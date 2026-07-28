# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from dataclasses import dataclass
from itertools import chain

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, format_amount


@dataclass
class RecognitionConfig:
    journal: object
    pl_account: object
    debit_bs_account: object
    credit_bs_account: object


class PerfObligation(models.Model):
    _name = "perf.obligation"
    _description = "Performance Obligation"
    _inherit = ["mail.thread"]

    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
    )
    perf_type = fields.Selection(
        selection=[
            ("income", "Income"),
            ("expense", "Expense"),
        ],
        string="Type",
        required=True,
        tracking=True,
    )
    name = fields.Char(
        copy=False,
        default="/",
        readonly=True,
        string="Reference",
        tracking=True,
    )
    total_amount = fields.Monetary(
        string="Total Amount to Recognize",
        required=True,
        tracking=True,
    )
    recognition_at_date_method = fields.Selection(
        selection=[],
        help="Method used to compute the amount to recognize at a given date. "
        "Leave empty for manual recognition only.",
        tracking=True,
    )
    move_line_ids = fields.One2many(
        comodel_name="account.move.line",
        inverse_name="perf_obligation_id",
        string="Journal Items",
        readonly=True,
    )
    move_line_count = fields.Integer(
        compute="_compute_move_line_count",
        string="Journal Items Count",
        readonly=True,
    )
    description = fields.Text(
        tracking=True,
    )
    supports_schedule = fields.Boolean(
        compute="_compute_supports_schedule",
        readonly=True,
    )
    schedule_income_line_ids = fields.One2many(
        comodel_name="perf.obligation.schedule.income",
        inverse_name="perf_obligation_id",
        string="Income Recognition Schedule",
        readonly=True,
    )
    schedule_expense_line_ids = fields.One2many(
        comodel_name="perf.obligation.schedule.expense",
        inverse_name="perf_obligation_id",
        string="Expense Recognition Schedule",
        readonly=True,
    )
    schedule_income_monthly_line_ids = fields.One2many(
        comodel_name="perf.obligation.schedule.income.monthly",
        inverse_name="perf_obligation_id",
        string="Income Recognition Schedule by Month",
        readonly=True,
    )
    schedule_expense_monthly_line_ids = fields.One2many(
        comodel_name="perf.obligation.schedule.expense.monthly",
        inverse_name="perf_obligation_id",
        string="Expense Recognition Schedule by Month",
        readonly=True,
    )
    schedule_needs_regeneration = fields.Boolean(
        default=False,
        index=True,
        copy=False,
        help="Set to True when the obligation's schedule may be "
        "out of date and needs to be regenerated. Cleared when "
        "regeneration completes.",
    )
    pl_account_id = fields.Many2one(
        comodel_name="account.account",
        string="P&L Recognition Account",
        check_company=True,
        tracking=True,
        help="Optional. If set, overrides the P&L account defined in the "
        "accounting configuration for recognition entries.",
    )
    invoiced_amount = fields.Monetary(
        compute="_compute_invoiced_amount",
        currency_field="currency_id",
        help="Total invoiced/billed amount for this obligation.",
    )
    is_over_invoiced = fields.Boolean(
        string="Over Invoiced",
        compute="_compute_is_over_invoiced",
        search="_search_is_over_invoiced",
    )

    def unlink(self):
        posted = self.env["account.move.line"].search(
            [
                ("perf_obligation_id", "in", self.ids),
                ("move_id.state", "=", "posted"),
            ],
            limit=1,
        )
        if posted:
            raise UserError(
                _(
                    "Cannot delete performance obligation '%(name)s': "
                    "it has posted accounting entries. "
                    "Consider updating the performance obligation amount to 0 if the "
                    "obligation has been cancelled.",
                    name=posted.perf_obligation_id.display_name,
                )
            )
        draft_schedule_moves = self.env["account.move"].search(
            [
                ("perf_obligation_schedule_move", "=", True),
                ("state", "=", "draft"),
                ("line_ids.perf_obligation_id", "in", self.ids),
            ]
        )
        if draft_schedule_moves:
            draft_schedule_moves.unlink()
        return super().unlink()

    @api.depends("recognition_at_date_method")
    def _compute_supports_schedule(self):
        for rec in self:
            rec.supports_schedule = rec._supports_schedule()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "name" not in vals or vals["name"] == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("perf.obligation")
        records = super().create(vals_list)
        records._mark_needs_recognition()
        return records

    def _compute_move_line_count(self):
        if not self.ids:
            for rec in self:
                rec.move_line_count = 0
            return
        count_per_obligation = self.env["account.move.line"]._read_group(
            domain=[
                ("perf_obligation_id", "in", self.ids),
                ("parent_state", "in", ("draft", "posted")),
            ],
            groupby=["perf_obligation_id"],
            aggregates=["__count"],
        )
        mapped = {po.id: count for po, count in count_per_obligation}
        for rec in self:
            rec.move_line_count = mapped.get(rec.id, 0)

    def action_view_move_lines(self):
        self.ensure_one()
        move_lines = self.move_line_ids.filtered(
            lambda line: line.parent_state in ("draft", "posted")
        )
        action = {
            "type": "ir.actions.act_window",
            "name": _("Journal Items"),
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "domain": [
                ("perf_obligation_id", "=", self.id),
                ("parent_state", "in", ("draft", "posted")),
            ],
            "context": {"create": False},
        }
        if len(move_lines) == 1:
            action.update({"view_mode": "form", "res_id": move_lines.id})
        return action

    def _get_recognition_config(self) -> RecognitionConfig:
        """Return recognition configuration for this obligation."""
        self.ensure_one()
        company = self.company_id
        prefix = "po_income" if self.perf_type == "income" else "po_expense"
        field_mapping = {
            "journal": "journal_id",
            "pl_account": "pl_account_id",
            "debit_bs_account": "debit_bs_account_id",
            "credit_bs_account": "credit_bs_account_id",
        }
        values = {}
        missing = []
        for attr, suffix in field_mapping.items():
            field_name = f"{prefix}_{suffix}"
            value = getattr(company, field_name)
            values[attr] = value
            if not value:
                field = self.env["res.company"]._fields[field_name]
                missing.append(field.string)
        if missing:
            raise ValidationError(
                _(
                    "Missing performance obligation configuration "
                    "on company '%(company)s' for %(perf_type)s: "
                    "%(fields)s",
                    company=company.name,
                    perf_type=self.perf_type,
                    fields=", ".join(missing),
                )
            )
        rc = RecognitionConfig(**values)
        if self.pl_account_id:
            rc.pl_account = self.pl_account_id
        if self.total_amount < 0:
            # swap debit and credit accounts
            rc.debit_bs_account, rc.credit_bs_account = (
                rc.credit_bs_account,
                rc.debit_bs_account,
            )
        return rc

    # ------------------------------------------------------------------
    # Recognition at date
    # ------------------------------------------------------------------

    def _supports_recognition_at_date(self):
        """Return whether this obligation supports automatic recognition
        at date computation.

        Override this method to add support for other recognition methods.
        """
        self.ensure_one()
        return bool(self.recognition_at_date_method)

    def _compute_amount_to_recognize_at_date(self, date):
        """Compute the cumulative amount to recognize at the given date.

        Dispatches to the method matching ``recognition_at_date_method``.
        Raises if no recognition method is configured.
        """
        self.ensure_one()
        if not self._supports_recognition_at_date():
            raise ValidationError(
                _(
                    "No recognition at date method configured "
                    "on performance obligation %(name)s.",
                    name=self.display_name,
                )
            )
        method_name = f"_compute_amount_to_recognize_{self.recognition_at_date_method}"
        compute_method = getattr(self, method_name, None)
        if compute_method is None:
            raise ValidationError(
                _(
                    "Unknown recognition method '%(method)s' "
                    "on performance obligation %(name)s.",
                    method=self.recognition_at_date_method,
                    name=self.display_name,
                )
            )
        return compute_method(date)

    # ------------------------------------------------------------------
    # Balance helpers
    # ------------------------------------------------------------------

    def _get_pl_internal_group(self):
        """Return the internal_group value for P&L accounts."""
        self.ensure_one()
        return self.perf_type  # "income" or "expense"

    def _get_income_or_expense_balance(self, date):
        """Get the balance of ALL P&L account lines linked to this
        obligation up to the given date.

        For income: sum of balances on income accounts (I).
        For expense: sum of balances on expense accounts (E).
        """
        self.ensure_one()
        [(balance,)] = self.env["account.move.line"]._read_group(
            domain=[
                ("perf_obligation_id", "=", self.id),
                ("parent_state", "in", ("draft", "posted")),
                ("date", "<=", date),
                (
                    "account_id.internal_group",
                    "=",
                    self._get_pl_internal_group(),
                ),
            ],
            groupby=[],
            aggregates=["balance:sum"],
        )
        return balance or 0.0

    def _get_bs_balances_by_account(self, date):
        """Return a dict {account_id: balance} for all balance sheet
        account lines linked to this obligation up to the given date.
        """
        self.ensure_one()
        balance_per_account = self.env["account.move.line"]._read_group(
            domain=[
                ("perf_obligation_id", "=", self.id),
                ("parent_state", "in", ("draft", "posted")),
                ("date", "<=", date),
                (
                    "account_id.account_type",
                    "in",
                    ("asset_current", "liability_current"),
                ),
            ],
            groupby=["account_id"],
            aggregates=["balance:sum"],
        )
        return {account.id: balance for account, balance in balance_per_account}

    # ------------------------------------------------------------------
    # Recognition logic
    # ------------------------------------------------------------------

    def _recognize(self, amount_to_recognize, date, description, schedule=False):
        """Compute and create a draft recognition journal entry at date
        for the desired amount.

        Returns the created account.move, or None if no adjustment is needed.
        """
        self.ensure_one()
        precision = self.company_id.currency_id.rounding

        amount_sign = float_compare(
            amount_to_recognize, 0, precision_rounding=precision
        )
        total_sign = float_compare(self.total_amount, 0, precision_rounding=precision)

        if amount_sign != 0 and amount_sign != total_sign:
            raise ValidationError(
                _(
                    "The amount to recognize must have the same sign as "
                    "the performance obligation amount "
                    "on performance obligation %(name)s.",
                    name=self.display_name,
                )
            )
        if (
            float_compare(
                abs(amount_to_recognize),
                abs(self.total_amount),
                precision_rounding=precision,
            )
            > 0
        ):
            raise ValidationError(
                _(
                    "The amount to recognize (%(amount)s) cannot exceed "
                    "the total amount on the performance obligation "
                    "(%(total)s) on performance obligation %(name)s.",
                    amount=amount_to_recognize,
                    total=self.total_amount,
                    name=self.display_name,
                )
            )

        config = self._get_recognition_config()

        lines = self._build_recognition_lines(
            amount_to_recognize, date, config, precision
        )

        if not lines:
            return None

        for line in lines:
            line["name"] = description

        move_vals = {
            "journal_id": config.journal.id,
            "date": date,
            "ref": f"{self.name} - {description}" if description else self.name,
            "line_ids": [Command.create(vals) for vals in lines],
        }
        if schedule:
            move_vals["perf_obligation_schedule_move"] = True
        return self.env["account.move"].create(move_vals)

    def _build_recognition_lines(self, amount_to_recognize, date, config, precision):
        """Return the list of line value-dicts for the recognition entry.

        Income:
          I = Income Balance (P&L accounts, linked to this obligation)
          R = amount_to_recognize (desired cumulative recognized income)
          DI = -R (desired income balance)
          X = DI - I = Balance Variation

        Expense:
          E = Expense Balance (P&L accounts, linked to this obligation)
          R = amount_to_recognize (desired cumulative recognized expense)
          DE = R (desired expense balance)
          X = DE - E

        Then:
          X < 0: add |X| debit to BS, credit |X| to PL
          X > 0: add |X| credit to BS, debit |X| to PL

        BS adjustments unwind existing opposite balances first,
        grouped by account.
        """
        is_income = self.perf_type == "income"

        # Step 1: Current P&L balance
        pl_balance = self._get_income_or_expense_balance(date)

        # Step 2: balance variation
        if is_income:
            balance_variation = -amount_to_recognize - pl_balance
        else:
            balance_variation = amount_to_recognize - pl_balance

        if float_is_zero(balance_variation, precision_rounding=precision):
            return []

        # Step 3: BS balances by account
        bs_balances = self._get_bs_balances_by_account(date)

        # Step 4: Build lines
        return self._build_lines(balance_variation, config, bs_balances, precision)

    def _build_lines(self, balance_variation, config, bs_balances, precision):
        """Build recognition lines.

        X < 0:
          - Debit each BS account with negative balance to bring it to 0,
            up to |X|.
          - Remaining: debit the configured debit_bs_account.
          - Credit PL for |X|.

        X > 0:
          - Credit each BS account with positive balance to bring it to 0,
            up to |X|.
          - Remaining: credit the configured credit_bs_account.
          - Debit PL for |X|.
        """
        lines = []
        abs_balance_variation = abs(balance_variation)

        if float_compare(balance_variation, 0, precision_rounding=precision) < 0:
            # X < 0: debit BS, credit PL
            remaining = abs_balance_variation

            for account_id, balance in bs_balances.items():
                if float_compare(balance, 0, precision_rounding=precision) < 0:
                    unwind = min(remaining, abs(balance))
                    if not float_is_zero(unwind, precision_rounding=precision):
                        lines.append(
                            self._make_line(account_id, debit=unwind, credit=0)
                        )
                        remaining -= unwind
                    if float_is_zero(remaining, precision_rounding=precision):
                        break

            if not float_is_zero(remaining, precision_rounding=precision):
                lines.append(
                    self._make_line(
                        config.debit_bs_account.id, debit=remaining, credit=0
                    )
                )

            lines.append(
                self._make_line(
                    config.pl_account.id,
                    debit=0,
                    credit=abs_balance_variation,
                )
            )

        elif float_compare(balance_variation, 0, precision_rounding=precision) > 0:
            # X > 0: credit BS, debit PL
            remaining = abs_balance_variation

            for account_id, balance in bs_balances.items():
                if float_compare(balance, 0, precision_rounding=precision) > 0:
                    unwind = min(remaining, balance)
                    if not float_is_zero(unwind, precision_rounding=precision):
                        lines.append(
                            self._make_line(account_id, debit=0, credit=unwind)
                        )
                        remaining -= unwind
                    if float_is_zero(remaining, precision_rounding=precision):
                        break

            if not float_is_zero(remaining, precision_rounding=precision):
                lines.append(
                    self._make_line(
                        config.credit_bs_account.id,
                        debit=0,
                        credit=remaining,
                    )
                )

            lines.append(
                self._make_line(
                    config.pl_account.id,
                    debit=abs_balance_variation,
                    credit=0,
                )
            )

        else:
            return []

        return lines

    def _make_line(self, account_id, debit, credit):
        """Return a journal item value-dict."""
        return {
            "account_id": account_id,
            "debit": debit,
            "credit": credit,
            "perf_obligation_id": self.id,
        }

    # ------------------------------------------------------------------
    # Schedule generation
    # ------------------------------------------------------------------

    def _get_schedule_dates(self):
        """Return the list of dates for which recognition schedule entries
        should be generated.

        Override this method to provide actual dates.
        Must return a list of date objects, sorted ascending.
        """
        self.ensure_one()
        raise NotImplementedError

    def _supports_schedule(self):
        """Return whether this obligation supports schedule generation.

        Override in modules that provide date ranges.
        """
        self.ensure_one()
        return False

    def action_generate_schedule(self):
        """UI action to regenerate recognition schedule entries."""
        for po in self:
            if not po._supports_schedule():
                raise ValidationError(
                    _(
                        "Schedule generation is not supported "
                        "on performance obligation %(name)s.",
                        name=po.display_name,
                    )
                )
            po._regenerate_schedule()

    def _regenerate_schedule(self):
        """Delete existing draft recognition moves and regenerate
        schedule entries, then clear the regeneration flag.

        If the obligation no longer supports schedule generation,
        do not regenerate schedule entries.
        """
        self.ensure_one()
        self = self.with_context(perf_obligation_in_regeneration=True)
        self._delete_draft_schedule_moves()
        if self._supports_schedule():
            self._generate_schedule_moves()
        self.write({"schedule_needs_regeneration": False})

    def _get_last_posted_recognition_date(self):
        """Return the date of the last posted recognition move for this
        obligation, or None if there are no posted recognition moves."""
        self.ensure_one()
        config = self._get_recognition_config()
        moves = self.env["account.move"].search(
            [
                ("journal_id", "=", config.journal.id),
                ("state", "=", "posted"),
                ("line_ids.perf_obligation_id", "=", self.id),
            ],
            order="date desc",
            limit=1,
        )
        return moves.date if moves else None

    def _get_draft_schedule_moves(self):
        """Return draft recognition moves automatically generated for this
        obligation and not yet posted."""
        self.ensure_one()
        return self.env["account.move"].search(
            [
                ("perf_obligation_schedule_move", "=", True),
                ("state", "=", "draft"),
                ("line_ids.perf_obligation_id", "=", self.id),
            ]
        )

    def _delete_draft_schedule_moves(self):
        """Delete all draft recognition journal entries linked to this
        obligation."""
        self.ensure_one()
        draft_moves = self._get_draft_schedule_moves()
        if draft_moves:
            draft_moves.unlink()

    def _generate_schedule_moves(self):
        """Generate draft recognition entries for each schedule date."""
        self.ensure_one()
        dates = self._get_schedule_dates()
        selection = dict(self._fields["perf_type"]._description_selection(self.env))
        perf_type_label = selection.get(self.perf_type, self.perf_type)
        for schedule_date in dates:
            amount = self._compute_amount_to_recognize_at_date(schedule_date)
            description = _(
                "%(type)s recognition %(date)s",
                type=perf_type_label,
                date=schedule_date,
            )
            self._recognize(
                amount_to_recognize=amount,
                date=schedule_date,
                description=description,
                schedule=True,
            )

    def _get_move_lines_date_range(self):
        """Return (min_date, max_date) of journal items linked to this
        obligation (draft or posted), or (False, False) if no lines.
        """
        self.ensure_one()
        [(min_date, max_date)] = self.env["account.move.line"]._read_group(
            domain=[
                ("perf_obligation_id", "=", self.id),
                ("parent_state", "in", ("draft", "posted")),
            ],
            groupby=[],
            aggregates=["date:min", "date:max"],
        )
        return min_date, max_date

    @api.model
    def _get_recognition_trigger_fields(self):
        """Return the list of fields whose modification should trigger
        schedule regeneration.

        Override this method in modules that add fields impacting
        the schedule (e.g. start_date, end_date).
        """
        return ["total_amount", "recognition_at_date_method", "pl_account_id"]

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = self._get_recognition_trigger_fields()
        if any(field in vals for field in trigger_fields):
            self._mark_needs_recognition()
        return res

    def _mark_needs_recognition(self, account_date=None):
        """Mark obligations as needing recognition review.

        Called whenever something changes that may affect the recognized
        amounts on an obligation: configuration changes, linked journal
        items being created/modified/removed, etc.

        :param account_date: optional earliest date from which recognition
            needs to be reviewed.

        For obligations that support schedule generation, this delegates
        to `_mark_for_regeneration` to flag the schedule for rebuild.
        Also flags obligations that no longer support scheduling but still
        have draft recognition moves pending cleanup.
        """
        if not self.env.context.get("perf_obligation_in_regeneration"):
            self.filtered(lambda po: po._supports_schedule())._mark_for_regeneration()
            self.filtered(
                lambda po: not po._supports_schedule()
                and bool(po._get_draft_schedule_moves())
            )._mark_for_regeneration()

    def _mark_for_regeneration(self):
        """Flag this obligation's schedule for regeneration."""
        self.with_context(perf_obligation_in_regeneration=True).write(
            {"schedule_needs_regeneration": True}
        )

    def _process_pending_regenerations(self):
        for po in self.filtered("schedule_needs_regeneration"):
            po._regenerate_schedule()

    def action_process_pending_regenerations(self):
        """List-view action: regenerate flagged obligations."""
        self._process_pending_regenerations()

    def _get_source_models(self):
        """Return all concrete models that inherit the source mixin."""
        SourceMixin = self.env.registry["perf.obligation.source.mixin"]
        return [
            self.env[name]
            for name in SourceMixin._inherit_children
            if not self.env[name]._abstract
        ]

    def _get_sources(self):
        """Return all source records pointing to this obligation,
        across all source models.
        """
        self.ensure_one()
        sources = []
        for model in self._get_source_models():
            records = (
                self.env[model._name]
                .with_context(active_test=False)
                .search([("perf_obligation_id", "=", self.id)])
            )
            if records:
                sources.append(records)
        return sources

    def _remove_source(self, source_record, reason=None):
        """Detach source_record from this obligation.

        If other sources remain, the obligation is kept and its total_amount
        is recomputed from what's left. If source_record was the sole source,
        the obligation is deleted.
        """
        self.ensure_one()
        source_record.perf_obligation_id = False
        if self._get_sources():
            new_amount = self._compute_total_amount_from_sources()
            self.sudo()._update_total_amount(
                new_amount,
                reason
                or _(
                    "Total amount recomputed after %(removed_source)s was removed; "
                    "obligation is still linked to other source(s).",
                    removed_source=source_record.display_name,
                ),
            )
        else:
            self.sudo().unlink()

    def _compute_total_amount_from_sources(self):
        """Sum the contribution of all sources linked to this obligation."""
        self.ensure_one()
        total = 0.0
        for source_records in self._get_sources():
            for record in source_records:
                total += record._get_perf_obligation_amount()
        return total

    def _update_total_amount(self, amount, reason):
        """Write total_amount and post a chatter message."""
        self.ensure_one()
        self._update_vals({"total_amount": amount}, reason)

    def _update_vals(self, vals, reason):
        """Update the obligation with *vals* if they differ from the current
        state, and log *reason* to the chatter.

        :param vals: dict of field values to sync (same format as write()).
        :param reason: human-readable explanation logged to the chatter.
        """
        self.ensure_one()
        self_sudo = self.sudo()
        current = self_sudo._convert_to_write({k: self_sudo[k] for k in vals})
        changed = {k: v for k, v in vals.items() if current.get(k) != v}
        if not changed:
            return
        self_sudo.write(changed)
        self_sudo._message_log(body=reason)

    def _update_amount_from_sources(self, reason=None):
        """Recompute total_amount from all linked sources and update it
        if it has changed.

        :param reason: optional human-readable reason for the update,
            included in the chatter message.
        """
        for obligation in self:
            sources = obligation._get_sources()
            if not sources:
                continue
            new_amount = obligation._compute_total_amount_from_sources()
            if (
                obligation.currency_id.compare_amounts(
                    new_amount, obligation.total_amount
                )
                == 0
            ):
                continue
            body = _(
                "Total amount updated to %(amount)s from source contributions.",
                amount=format_amount(
                    self.env,
                    new_amount,
                    obligation.currency_id or self.env.company.currency_id,
                ),
            )
            if reason:
                body += " " + reason
            obligation._update_total_amount(new_amount, body)

    def _get_invoiced_amount(self):
        """Return the invoiced/billed amount for this obligation.

        Income: -(income account balance) - (BS account balance)
        Expense: (expense account balance) + (BS account balance)
        """
        self.ensure_one()
        [(pl_balance,)] = self.env["account.move.line"]._read_group(
            domain=[
                ("perf_obligation_id", "=", self.id),
                ("parent_state", "in", ("draft", "posted")),
                ("account_id.internal_group", "=", self._get_pl_internal_group()),
            ],
            aggregates=["balance:sum"],
        )
        [(bs_balance,)] = self.env["account.move.line"]._read_group(
            domain=[
                ("perf_obligation_id", "=", self.id),
                ("parent_state", "in", ("draft", "posted")),
                (
                    "account_id.account_type",
                    "in",
                    ("asset_current", "liability_current"),
                ),
            ],
            aggregates=["balance:sum"],
        )
        pl_balance = pl_balance or 0.0
        bs_balance = bs_balance or 0.0
        if self.perf_type == "income":
            amount = -pl_balance - bs_balance
        elif self.perf_type == "expense":
            amount = pl_balance + bs_balance
        return amount

    def _compute_invoiced_amount(self):
        for rec in self:
            rec.invoiced_amount = rec._get_invoiced_amount()

    @api.depends("invoiced_amount", "total_amount")
    def _compute_is_over_invoiced(self):
        for rec in self:
            rec.is_over_invoiced = rec.invoiced_amount > rec.total_amount

    @api.model
    def _search_is_over_invoiced(self, operator, value):
        """Search method returning POs where invoiced_amount > total_amount."""
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise UserError(_("Unsupported search operator or value."))
        positive = (operator == "=" and value) or (operator == "!=" and not value)
        pl_groups = self.env["account.move.line"]._read_group(
            domain=[
                ("perf_obligation_id", "!=", False),
                ("parent_state", "in", ("draft", "posted")),
                ("account_id.internal_group", "in", ("income", "expense")),
            ],
            groupby=["perf_obligation_id", "account_id"],
            aggregates=["balance:sum"],
        )
        bs_groups = self.env["account.move.line"]._read_group(
            domain=[
                ("perf_obligation_id", "!=", False),
                ("parent_state", "in", ("draft", "posted")),
                (
                    "account_id.account_type",
                    "in",
                    ("asset_current", "liability_current"),
                ),
            ],
            groupby=["perf_obligation_id"],
            aggregates=["balance:sum"],
        )
        pl_balances = {}
        for po, account, bal_sum in pl_groups:
            key = (po.id, account.internal_group)
            pl_balances[key] = pl_balances.get(key, 0.0) + (bal_sum or 0.0)
        bs_balances = {po.id: bal_sum or 0.0 for po, bal_sum in bs_groups}
        po_ids_with_lines = set(po.id for po, _, _ in pl_groups) | set(
            bs_balances.keys()
        )
        pos = self.browse(po_ids_with_lines)
        matching_ids = []
        for po in pos:
            pl_bal = pl_balances.get((po.id, po._get_pl_internal_group()), 0.0)
            bs_bal = bs_balances.get(po.id, 0.0)
            if po.perf_type == "income":
                invoiced = -pl_bal - bs_bal
            else:
                invoiced = pl_bal + bs_bal
            if invoiced > po.total_amount:
                matching_ids.append(po.id)
        return [("id", "in" if positive else "not in", matching_ids)]

    def _ensure_sole_source(self, source_record):
        """Raise if source_record is not the sole source of this obligation."""
        self.ensure_one()
        sources = self._get_sources()
        sole = len(sources) == 1 and sources[0] == source_record
        if not sole:
            all_sources = ", ".join(
                r.display_name for r in chain.from_iterable(sources)
            )
            raise ValidationError(
                _(
                    "Performance obligation %(obligation)s originates from "
                    "multiple sources %(sources)s, so it can't be updated "
                    "automatically to match %(record)s.",
                    obligation=self.display_name,
                    sources=all_sources,
                    record=source_record.display_name,
                )
            )

    def _get_recognition_journals(self):
        """Return the recognition journals (income and expense) configured
        on the companies of the obligations in self."""
        return self._get_recognition_journals_for_companies(self.company_id)

    @api.model
    def _get_recognition_journals_for_companies(self, companies):
        """Return the recognition journals (income and expense) configured
        on the given companies."""
        return companies.po_income_journal_id | companies.po_expense_journal_id

    def _check_blocking_draft_moves(self, date, companies=None):
        """Raise a UserError if there are draft journal entries, with at
        least one line linked to a performance obligation, dated on or
        before *date*, posted in a company of one of the obligations in
        self (or in *companies* if given), and posted in a journal other
        than the configured income/expense recognition journals.

        :param companies: optional company scope to use instead of
            ``self.company_id``. Required when *self* is empty, e.g. when
            checking across all obligations without materializing them.
        """
        companies = self.company_id if companies is None else companies
        reco_journals = self._get_recognition_journals_for_companies(companies)
        domain = [
            ("company_id", "in", companies.ids),
            ("state", "=", "draft"),
            ("date", "<=", date),
            ("line_ids.perf_obligation_id", "!=", False),
            ("journal_id", "not in", reco_journals.ids),
        ]
        if self:
            domain.append(("line_ids.perf_obligation_id", "in", self.ids))
        limit = 10
        blocking_moves = self.env["account.move"].search(domain, limit=limit)
        if blocking_moves:
            total = self.env["account.move"].search_count(domain)
            moves_text = "\n".join(
                f"- {move.name or move.ref or move.id} "
                f"({move.journal_id.display_name}, {move.date})"
                for move in blocking_moves
            )
            if total > limit:
                moves_text += "\n" + _("... and %(count)s more", count=total - limit)
            raise UserError(
                _(
                    "Cannot post performance obligation recognition entries "
                    "on or before %(date)s: the following draft journal "
                    "entries are linked to a performance obligation and are "
                    "not in a recognition journal. Please post or remove "
                    "them first:\n%(moves)s",
                    date=date,
                    moves=moves_text,
                )
            )

    @api.model
    def _post_recognition_moves(self, date, obligations=None, companies=None):
        """Mark eligible draft recognition moves dated on or before *date*
        for auto-posting, and trigger the auto-post mechanism.

        :param obligations: if given, restrict to moves with at least one
            line linked to one of these performance obligations. If not
            given, all performance obligations are eligible.
        :param companies: company scope for the recognition journals and
            the blocking-moves check. Defaults to the companies of
            *obligations*, or ``self.env.companies`` if *obligations* is
            also not given.
        """
        if companies is None:
            companies = obligations.company_id if obligations else self.env.companies
        reco_journals = self._get_recognition_journals_for_companies(companies)
        domain = [
            ("journal_id", "in", reco_journals.ids),
            ("state", "=", "draft"),
            ("date", "<=", date),
        ]
        if obligations is not None:
            domain.append(("line_ids.perf_obligation_id", "in", obligations.ids))
        else:
            domain.append(("line_ids.perf_obligation_id", "!=", False))
        moves = self.env["account.move"].search(domain)
        if moves:
            involved_obligations = moves.line_ids.perf_obligation_id
            involved_obligations._check_blocking_draft_moves(date, companies=companies)
            moves.write({"auto_post": "at_date", "checked": True})
            self.env.ref("account.ir_cron_auto_post_draft_entry")._trigger()

    def action_post_recognition_moves(self, date):
        """UI action: mark eligible draft recognition moves linked to the
        obligations in self for auto-posting."""
        self._post_recognition_moves(date, obligations=self)

    @api.model
    def _post_all_recognition_moves(self, date, companies=None):
        """Mark all eligible draft recognition moves dated on or before
        *date* for auto-posting, across all performance obligations.

        Unlike `action_post_recognition_moves`, this does not filter by a
        specific set of performance obligations, so it scales independently
        of the number of obligations pending posting.
        """
        self._post_recognition_moves(date, companies=companies)

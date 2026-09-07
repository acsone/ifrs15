# Copyright 2026 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "Performance Obligations (IFRS 15)",
    "summary": """Manage Performance Obligations for income and expense recognition
     according to IFRS 15""",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "license": "LGPL-3",
    "author": "ACSONE SA/NV",
    "website": "https://github.com/acsone/account-performance-obligation",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "data/ir_sequence.xml",
        "views/res_config_settings.xml",
        "views/account_move_line.xml",
        "views/perf_obligation.xml",
        "views/perf_obligation_schedule.xml",
        "views/ir_ui_menu.xml",
        "wizards/perf_obligation_post_recognition_moves.xml",
        "wizards/perf_obligation_recognize.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_perf_obligation/static/src/css/perf_obligation.css",
        ],
    },
}

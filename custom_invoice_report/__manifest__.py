# -*- coding: utf-8 -*-
###############################################################################
#
#    Pixelwave Software
#
#    Copyright (C) 2024-TODAY Pixelwave Infotech(<https://www.pixelwaveinfotech.com>)
#    Author: Milan Hirani(pixelwaveinfotech@gmail.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
###############################################################################
{
    "name": "Custom Invoice Report",
    "summary": "Add QR-code in invoice report",
    "author": "Ahmed Abo EL-Atta",
    "website": "https://www.linkedin.com/in/ahmedaboelatta/",
    "category": "account",
    "version": "18.0.1.0.1",
    'depends': ['base', 'account', 'payment', 'l10n_gcc_invoice'],
    "data": [
        "views/report_invoice.xml"
    ],
    'images': [],
    'license': 'OPL-1',
    'price': 0,
    'currency': 'USD',
}

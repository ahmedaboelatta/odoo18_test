{
    'name': 'Recycle Bin',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Soft-delete records and restore them later',
    'author': 'Ahmed Abo EL-Atta',
    'website': 'https://www.linkedin.com/in/ahmedaboelatta/',
    'depends': ['base', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/recycle_bin_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

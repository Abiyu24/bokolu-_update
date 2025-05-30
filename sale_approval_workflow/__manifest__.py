{
    'name': 'Sale Approval Workflow',
    'version': '1.0',
    'depends': ['sale'],
    'data': [
        'security/sale_approval_security.xml',
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
}

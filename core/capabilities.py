# Every named permission in the system. Add new ones here, then run makemigrations.
CAPABILITIES = {
    'view_students': 'View students',
    'manage_students': 'Add and edit students',
    'view_attendance': 'View attendance',
    'mark_attendance': 'Mark attendance',
    'view_grades': 'View grades',
    'enter_grades': 'Enter grades',
    'setup_assessments': 'Set up assessments',
    'lock_results': 'Lock and unlock results',
    'comment_report_cards': 'Add report card comments',
    'generate_report_cards': 'Generate report cards',
    'approve_report_cards': 'Approve and sign report cards',
    'view_fees': 'View fee records',
    'collect_fees': 'Record fee payments',
    'manage_users': 'Manage staff accounts',
    'reverse_payments': 'Reverse payments',
    'grant_discounts': 'Grant fee discounts',
}
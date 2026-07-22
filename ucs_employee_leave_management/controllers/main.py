from odoo import http
from odoo.http import request
from odoo.addons.ucs_portal_self_service.controllers.main import CustomCustomerPortal
from datetime import date

class LeaveManagementCustomerPortal(CustomCustomerPortal):

    @http.route(['/my/dashboard'], type='http', auth="user", website=True)
    def employee_dashboard(self, **kw):
        # Call the original dashboard logic to get all other context values
        response = super().employee_dashboard(**kw)
        
        # If it's not a standard render response, return as is
        if not hasattr(response, 'qcontext'):
            return response

        values = response.qcontext
        
        # Ensure we only process if it's an employee
        if values.get('is_employee'):
            employee = values.get('employee')
            
            # Recursive function to get all subordinate employee ids
            def get_all_subordinates(emp):
                subs = emp.subordinate_ids
                all_subs = subs
                for sub in subs:
                    all_subs |= get_all_subordinates(sub)
                return all_subs
            
            all_emps = get_all_subordinates(employee) | employee
            today = date.today()
            
            # Hierarchy Leaves Logic (Current User + Subordinates for Current Month)
            values['hierarchy_leaves'] = request.env['hr.leave'].sudo().browse()
            
            # Start and End of current month
            import calendar
            start_of_month = today.replace(day=1)
            end_of_month = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            
            start_m_str = start_of_month.strftime('%Y-%m-%d 00:00:00')
            end_m_str = end_of_month.strftime('%Y-%m-%d 23:59:59')
            today_str = today.strftime('%Y-%m-%d 00:00:00')
            
            leave_emp_ids = all_emps.ids
            
            if leave_emp_ids:
                leaves_domain = [
                    ('employee_id', 'in', leave_emp_ids),
                    ('state', 'not in', ['cancel', 'refuse']),
                    ('request_date_from', '<=', end_m_str),
                    ('request_date_to', '>=', today_str)
                ]
                values['hierarchy_leaves'] = request.env['hr.leave'].sudo().search(leaves_domain, order='request_date_from asc')

        # We need to re-render since we modified qcontext. Actually qcontext is passed by reference.
        # But we can just return the response directly since qcontext is updated.
        return response

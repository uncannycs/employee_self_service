# -*- coding: utf-8 -*-
import io
import base64
import datetime
from odoo import http, fields, _
from odoo.http import request, content_disposition
import xlsxwriter

class TimesheetExportController(http.Controller):
    """
    Controller responsible for generating and exporting Employee Timesheet Summary
    Excel (.xlsx) reports from the Employee Self Service Portal.
    """

    def _format_float_time(self, hours):
        """ Helper utility method to format float hours into HH:MM string representation. """
        h = int(hours or 0)
        m = int(round((hours - h) * 60))
        if m >= 60:
            h += 1
            m = 0
        return f"{h:02d}:{m:02d}"

    @http.route(['/my/timesheets/export'], type='http', auth="user", methods=['GET', 'POST'], website=True)
    def portal_timesheets_export_excel(self, **kw):
        """
        Generate and download a clean, attractive Excel (.xlsx) report of timesheet records.
        Header merges columns A to I with centered Company Name (17pt), centered Sub-title (11pt),
        gridlines hidden to eliminate red dividing lines, and Company Logo positioned right next to Company Name.
        """
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)

        is_manager = (
            user.has_group('base.group_erp_manager') or
            user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_admin') or
            user.has_group('ucs_employee_timesheet_approval.group_portal_timesheet_approval_manager') or
            user.has_group('hr_timesheet.group_timesheet_manager') or
            user.has_group('hr_timesheet.group_hr_timesheet_approver')
        )

        scope = kw.get('scope', 'my')
        date_from = kw.get('date_from')
        date_to = kw.get('date_to')
        project_id = kw.get('project_id')
        filterby = kw.get('filterby', 'all')
        search_query = kw.get('search', '').strip()
        timesheet_ids_raw = kw.get('timesheet_ids') or request.params.get('timesheet_ids')

        # Build Domain based on User Scope and Permissions
        domain = [('project_id', '!=', False)]

        # Check if specific timesheet IDs are selected via checkboxes
        if timesheet_ids_raw:
            if isinstance(timesheet_ids_raw, str):
                selected_ids = [int(i) for i in timesheet_ids_raw.split(',') if i.strip().isdigit()]
            elif isinstance(timesheet_ids_raw, list):
                selected_ids = [int(i) for i in timesheet_ids_raw if str(i).isdigit()]
            else:
                selected_ids = []

            if selected_ids:
                domain.append(('id', 'in', selected_ids))

        if scope == 'all' and is_manager:
            # Manager/Admin scope: all allowed timesheets
            pass
        else:
            # Employee scope: only own timesheets
            if employee:
                domain.append(('employee_id', '=', employee.id))
            else:
                domain.append(('user_id', '=', user.id))

        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        if project_id and project_id.isdigit():
            domain.append(('project_id', '=', int(project_id)))
        if filterby and filterby != 'all':
            domain.append(('state', '=', filterby))
        if search_query:
            domain.append('|')
            domain.append(('name', 'ilike', search_query))
            domain.append(('project_id.name', 'ilike', search_query))

        timesheet_records = request.env['account.analytic.line'].sudo().search(domain, order="date desc, employee_id asc, id desc")

        # Create Excel Workbook in Memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Timesheets Summary')

        # Hide Gridlines so no red/grey row lines appear on screen
        worksheet.hide_gridlines(2)

        # Set Column Widths for Optimal Spacing
        worksheet.set_column('A:A', 8)    # S.No.
        worksheet.set_column('B:B', 14)   # Date
        worksheet.set_column('C:C', 24)   # Employee Name
        worksheet.set_column('D:D', 28)   # Project / Logo column D
        worksheet.set_column('E:E', 28)   # Task
        worksheet.set_column('F:F', 42)   # Description
        worksheet.set_column('G:G', 18)   # Hours (HH:MM)
        worksheet.set_column('H:H', 16)   # Hours (Float)
        worksheet.set_column('I:I', 16)   # Status

        # Set Row Heights for Clean Header Banner & Logo
        worksheet.set_row(0, 36) # Row 1 (Company Name Banner - Centered)
        worksheet.set_row(1, 24) # Row 2 (EMPLOYEE TIMESHEET SUMMARY REPORT Sub-line - Centered)
        worksheet.set_row(2, 10) # Row 3 (Spacing Row)
        worksheet.set_row(3, 28) # Row 4 (Table Header Row)

        # Define Styles & Color Palette (Deep Purple Theme: #4a148c / #3b0764, NO borders)
        fmt_bg = workbook.add_format({'bg_color': '#4a148c', 'border': 0})
        fmt_company_title = workbook.add_format({
            'bold': True,
            'font_size': 17,
            'font_color': '#ffffff',
            'bg_color': '#4a148c',
            'align': 'center',
            'valign': 'vcenter',
            'border': 0
        })
        fmt_report_subtitle = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'font_color': '#f3e8ff',
            'bg_color': '#4a148c',
            'align': 'center',
            'valign': 'vcenter',
            'border': 0
        })

        # Table Header Format
        fmt_th = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'font_color': '#ffffff',
            'bg_color': '#4c1d95',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'border_color': '#3b0764'
        })

        # Data Cell Formats (With Alternating Row Colors)
        fmt_cell_center_1 = workbook.add_format({'font_size': 10, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0', 'bg_color': '#ffffff'})
        fmt_cell_center_2 = workbook.add_format({'font_size': 10, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0', 'bg_color': '#fcfcfd'})

        fmt_cell_left_1 = workbook.add_format({'font_size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0', 'bg_color': '#ffffff'})
        fmt_cell_left_2 = workbook.add_format({'font_size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0', 'bg_color': '#fcfcfd'})

        fmt_cell_right_1 = workbook.add_format({'font_size': 10, 'align': 'right', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0', 'bg_color': '#ffffff', 'num_format': '#,##0.00'})
        fmt_cell_right_2 = workbook.add_format({'font_size': 10, 'align': 'right', 'valign': 'vcenter', 'border': 1, 'border_color': '#e2e8f0', 'bg_color': '#fcfcfd', 'num_format': '#,##0.00'})
        
        # Status Cell Formats
        status_styles = {
            'draft': workbook.add_format({'font_size': 10, 'bold': True, 'font_color': '#475569', 'bg_color': '#f1f5f9', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#cbd5e1'}),
            'confirm': workbook.add_format({'font_size': 10, 'bold': True, 'font_color': '#c2410c', 'bg_color': '#ffedd5', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#fdba74'}),
            'approved': workbook.add_format({'font_size': 10, 'bold': True, 'font_color': '#15803d', 'bg_color': '#dcfce7', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#86efac'}),
            'refused': workbook.add_format({'font_size': 10, 'bold': True, 'font_color': '#b91c1c', 'bg_color': '#fee2e2', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'border_color': '#fca5a5'}),
        }

        # Total Row Format
        fmt_total_label = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': '#1e1b4b', 'bg_color': '#e0e7ff',
            'align': 'right', 'valign': 'vcenter', 'top': 2, 'bottom': 6, 'top_color': '#4338ca', 'bottom_color': '#4338ca'
        })
        fmt_total_val = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': '#4338ca', 'bg_color': '#e0e7ff',
            'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0.00',
            'top': 2, 'bottom': 6, 'top_color': '#4338ca', 'bottom_color': '#4338ca'
        })
        fmt_total_center = workbook.add_format({
            'bold': True, 'font_size': 11, 'font_color': '#4338ca', 'bg_color': '#e0e7ff',
            'align': 'center', 'valign': 'vcenter',
            'top': 2, 'bottom': 6, 'top_color': '#4338ca', 'bottom_color': '#4338ca'
        })

        # --- WRITE BANNER: MERGE COLUMNS A TO I & CENTER TEXT ---
        company = request.env.company
        company_name = (company.name or 'EMPLOYEE SELF SERVICE').upper()

        # Fill background for rows 0 and 1
        for col_idx in range(9):
            worksheet.write(0, col_idx, '', fmt_bg)
            worksheet.write(1, col_idx, '', fmt_bg)

        worksheet.merge_range('A1:I1', company_name, fmt_company_title)
        worksheet.merge_range('A2:I2', 'EMPLOYEE TIMESHEET SUMMARY REPORT', fmt_report_subtitle)

        # Insert Company Logo Right Next to Centered Company Name (Cell D1 with x_offset)
        if company.logo:
            try:
                logo_bytes = base64.b64decode(company.logo)
                image_stream = io.BytesIO(logo_bytes)
                worksheet.insert_image('D1', 'company_logo.png', {
                    'image_data': image_stream,
                    'x_scale': 0.32,
                    'y_scale': 0.32,
                    'x_offset': 110,
                    'y_offset': 8,
                })
            except Exception:
                pass

        # Write Table Column Headers (Row 4 - Index 3)
        headers = ['S.No.', 'Date', 'Employee', 'Project', 'Task', 'Description', 'Logged (HH:MM)', 'Hours (Float)', 'Status']
        for col_idx, h_text in enumerate(headers):
            worksheet.write(3, col_idx, h_text, fmt_th)

        # Write Data Rows
        start_row = 4
        current_row = start_row

        status_labels = {
            'draft': 'Draft',
            'confirm': 'Submitted',
            'approved': 'Approved',
            'refused': 'Refused'
        }

        tot_hours = sum(timesheet_records.mapped('unit_amount'))

        for idx, line in enumerate(timesheet_records, 1):
            st = line.state or 'draft'
            st_fmt = status_styles.get(st, fmt_cell_center_1)
            st_label = status_labels.get(st, st.capitalize())

            # Row styling
            f_center = fmt_cell_center_1 if idx % 2 != 0 else fmt_cell_center_2
            f_left = fmt_cell_left_1 if idx % 2 != 0 else fmt_cell_left_2
            f_right = fmt_cell_right_1 if idx % 2 != 0 else fmt_cell_right_2

            worksheet.set_row(current_row, 20)
            worksheet.write(current_row, 0, idx, f_center)
            worksheet.write(current_row, 1, str(line.date or ''), f_center)
            worksheet.write(current_row, 2, line.employee_id.name or (line.user_id.name if line.user_id else '-'), f_left)
            worksheet.write(current_row, 3, line.project_id.name or '-', f_left)
            worksheet.write(current_row, 4, line.task_id.name if line.task_id else '-', f_left)
            worksheet.write(current_row, 5, line.name or '-', f_left)
            worksheet.write(current_row, 6, self._format_float_time(line.unit_amount), f_center)
            worksheet.write(current_row, 7, line.unit_amount or 0.0, f_right)
            worksheet.write(current_row, 8, st_label, st_fmt)

            current_row += 1

        # Write Total Formula Row
        worksheet.set_row(current_row, 22)
        worksheet.merge_range(f'A{current_row + 1}:F{current_row + 1}', 'TOTAL LOGGED HOURS', fmt_total_label)
        worksheet.write(current_row, 6, self._format_float_time(tot_hours), fmt_total_center)

        if current_row > start_row:
            formula = f"=SUM(H{start_row + 1}:H{current_row})"
            worksheet.write_formula(current_row, 7, formula, fmt_total_val, tot_hours)
        else:
            worksheet.write(current_row, 7, 0.0, fmt_total_val)

        worksheet.write(current_row, 8, '', fmt_total_center)

        # Close Workbook and Prepare Download Response
        workbook.close()
        output.seek(0)

        file_date_str = fields.Date.today().strftime('%Y%m%d')
        filename = f"Timesheet_Report_{file_date_str}.xlsx"

        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename)),
            ]
        )

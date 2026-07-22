import re

with open('views/portal_templates.xml', 'r') as f:
    content = f.read()

# 1. Remove Leaves Card
# We need to find: <a href="/my/leaves" class="ess-split-card"> ... </a>
start_idx = content.find('<a href="/my/leaves" class="ess-split-card">')
if start_idx != -1:
    end_idx = content.find('</a>', start_idx) + 4
    # Include the comment above it
    comment_idx = content.rfind('<!-- 3. Leaves -->', 0, start_idx)
    if comment_idx != -1:
        start_idx = comment_idx
    content = content[:start_idx] + content[end_idx:]

# 2. Remove Approvals Card
start_idx = content.find('<t t-if="request.env.user.has_group(\'ucs_portal_self_service.group_portal_approval_manager\')">')
if start_idx != -1:
    end_idx = content.find('</t>', start_idx) + 4
    # Include the comment above it
    comment_idx = content.rfind('<!-- 5. Approvals (Only for Managers & Admins) -->', 0, start_idx)
    if comment_idx != -1:
        start_idx = comment_idx
    content = content[:start_idx] + content[end_idx:]

# 3. Remove Team Leaves Row
start_idx = content.find('<div class="row mt-4">\n                            <!-- Right: Team Leaves -->')
if start_idx != -1:
    # Need to match the closing div of this row
    # The row has: div.row -> div.col-lg-12 -> div.card -> div.card-header, div.card-body
    # We can just use string slice since it's a known chunk until </t>
    end_idx = content.find('</t>', start_idx)
    # Actually wait, the `</t>` is after the row closes. Let's find the `</div>` that matches `row mt-4`.
    # It is right before `</t>`
    end_row = content.find('</div>', end_idx - 30) # roughly
    content = content[:start_idx] + content[end_idx:]

with open('views/portal_templates.xml', 'w') as f:
    f.write(content)

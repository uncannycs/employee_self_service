import re

with open('views/portal_templates.xml', 'r') as f:
    content = f.read()

# 1. Extract Deadlines Block
start_deadlines = content.find('<!-- Left: Team Task Deadlines -->')
end_deadlines = content.find('<!-- Right: Team Leaves -->')
deadlines_block = content[start_deadlines:end_deadlines]

# We need the inner content of deadlines to copy for in-progress tasks
# Actually, let's just make the in-progress block manually replacing some strings from deadlines block
in_progress_block = deadlines_block.replace('<!-- Left: Team Task Deadlines -->', '<!-- Right: In-Progress Tasks -->')
in_progress_block = in_progress_block.replace('<t t-esc="tasks_heading"/>', 'In-Progress Tasks')
in_progress_block = in_progress_block.replace('hierarchy_tasks', 'in_progress_tasks')
in_progress_block = in_progress_block.replace('No tasks found!', 'No in-progress tasks!')

# 2. Extract Team Leaves Block
start_leaves = content.find('<!-- Right: Team Leaves -->')
end_leaves = content.find('</div>\n                        </div>\n                    </t>\n\n                    <!-- Tier 2:')
leaves_block = content[start_leaves:end_leaves]

# 3. Create the new row for Team Leaves
# We want it to be col-lg-12 instead of col-lg-6, so we'll replace col-lg-6 with col-lg-12
new_leaves_row = '\n                        <div class="row mt-4">\n                            ' + leaves_block.replace('col-lg-6', 'col-lg-12') + '\n                        </div>'

# 4. Replace in original content
new_content = content[:start_leaves] + in_progress_block + content[end_leaves:end_leaves + 73] + new_leaves_row + content[end_leaves + 73:]

# wait, let's check end_leaves + 73 is actually correct? No, let's just use string replacement nicely.
new_middle_grid = deadlines_block + in_progress_block

# Find the start of middle grid
start_middle = content.find('<!-- Left: Team Task Deadlines -->')
end_middle = end_leaves # The end of the right column

# Let's replace the whole row
row_end_tag = '                        </div>\n                    </t>'
end_row_idx = content.find(row_end_tag, start_leaves)

new_content = content[:start_middle] + new_middle_grid + '                        </div>\n' + new_leaves_row + '\n                    </t>' + content[end_row_idx + len(row_end_tag):]

with open('views/portal_templates.xml', 'w') as f:
    f.write(new_content)

print("Modification done!")

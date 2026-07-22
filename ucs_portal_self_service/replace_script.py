import re

with open('views/portal_templates.xml', 'r') as f:
    content = f.read()

# 1. Extract the Team Leaves block
team_leaves_start = content.find('<!-- Right: Team Leaves -->')
# Find the end of the col-lg-6 block for Team Leaves
# It ends with:
#                                                             </td>
#                                                         </tr>
#                                                     </t>
#                                                 </tbody>
#                                             </table>
#                                         </div>
#                                     </div>
#                                 </div>
#                             </div>
team_leaves_end = content.find('</div>\n                            \n                            <!-- Bottom: Upcoming Birthdays', team_leaves_start)
if team_leaves_end == -1:
    team_leaves_end = content.find('</div>\n                            \n                            <div class="row mt-4">', team_leaves_start)
if team_leaves_end == -1:
    # Just search for the end of the col-lg-6 div
    team_leaves_end = content.find('</div>\n                            </div>\n                        </div>\n', team_leaves_start)
    if team_leaves_end != -1:
        team_leaves_end += len('</div>\n                            </div>\n')
    else:
        # Fallback manual find
        team_leaves_end = content.find('<!-- Middle Grid end -->') # Not exist
        pass

# Let's do it safely. The team leaves block is exactly between "<!-- Right: Team Leaves -->" and the end of the <div class="row mt-4"> which contains both left and right columns.
# Wait, let's just use string replacement.

# We will read lines and process them.
lines = content.split('\n')
new_lines = []
in_team_leaves = False
team_leaves_lines = []

for line in lines:
    if '<!-- Right: Team Leaves -->' in line:
        in_team_leaves = True
    
    if in_team_leaves:
        team_leaves_lines.append(line)
        if '<!-- End Right: Team Leaves -->' in line or ('</div>' in line and len(team_leaves_lines) > 60 and '</div>' in team_leaves_lines[-2] and '</div>' in team_leaves_lines[-3]):
            pass # wait, this is risky.

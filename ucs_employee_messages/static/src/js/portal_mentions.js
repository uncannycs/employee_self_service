/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

class MentionAutocomplete {
    constructor(textarea, model, resId) {
        this.$textarea = $(textarea);
        this.model = model;
        this.resId = resId;
        this.mentionedPartners = [];
        this.$dropdown = null;
        this.currentTerm = '';
        this.cursorPos = 0;
        this.mentionStartIndex = -1;
        this.suggestions = [];
        this.activeIndex = 0;
        
        console.log("MentionAutocomplete initialized for model:", model, "resId:", resId);

        this._setup();
    }

    _setup() {
        this.$textarea.on('input', this._onInput.bind(this));
        this.$textarea.on('keydown', this._onKeydown.bind(this));
        this.$textarea.on('click keyup', this._updateCursorPos.bind(this));
        
        // Hide dropdown when clicking outside
        $(document).on('click', (e) => {
            if (this.$dropdown && !this.$dropdown.is(e.target) && this.$dropdown.has(e.target).length === 0) {
                this._hideDropdown();
            }
        });
    }

    _updateCursorPos(e) {
        if (e.type === 'keyup' && ['ArrowUp', 'ArrowDown', 'Enter'].includes(e.key)) {
            return; // Handled by keydown
        }
        this.cursorPos = this.$textarea[0].selectionStart;
        if (this.$dropdown) {
            this._checkMentionContext();
        }
    }

    _onInput(e) {
        this.cursorPos = this.$textarea[0].selectionStart;
        this._checkMentionContext();
    }

    _checkMentionContext() {
        const text = this.$textarea.val();
        const textBeforeCursor = text.substring(0, this.cursorPos);
        
        // Find the last '@' before the cursor
        const lastAt = textBeforeCursor.lastIndexOf('@');
        
        if (lastAt !== -1) {
            // Check if '@' is at the start of string or preceded by space/newline
            if (lastAt === 0 || [' ', '\n'].includes(textBeforeCursor.charAt(lastAt - 1))) {
                const term = textBeforeCursor.substring(lastAt + 1);
                // Only allow valid characters in term (no spaces)
                // Actually, let's allow spaces if we want to search full names, but stop at newline
                if (!term.includes('\n')) {
                    this.mentionStartIndex = lastAt;
                    this.currentTerm = term;
                    this._fetchSuggestions();
                    return;
                }
            }
        }
        this._hideDropdown();
    }

    async _fetchSuggestions() {
        if (!this.model || !this.resId) return;

        try {
            const result = await rpc('/my/mentions/suggest', {
                model: this.model,
                res_id: this.resId,
                term: this.currentTerm
            });
            this.suggestions = result;
            this._renderDropdown();
        } catch (e) {
            console.error("Error fetching mentions:", e);
            alert("Mention error: " + (e.message || JSON.stringify(e)));
            this._hideDropdown();
        }
    }

    _renderDropdown() {
        if (!this.suggestions.length) {
            this._hideDropdown();
            return;
        }

        if (!this.$dropdown) {
            this.$dropdown = $('<ul class="ess-mention-dropdown list-group"></ul>');
            
            // Insert dropdown right after the textarea in the DOM (assuming relatively positioned parent)
            this.$textarea.after(this.$dropdown);
        }

        this.$dropdown.empty();
        this.activeIndex = 0;

        this.suggestions.forEach((user, index) => {
            const $item = $(`<li class="list-group-item ess-mention-item ${index === 0 ? 'active' : ''}" data-id="${user.id}">
                ${user.name}
            </li>`);
            $item.on('mousedown', (e) => {
                e.preventDefault(); // prevent losing focus
                this._selectUser(user);
            });
            this.$dropdown.append($item);
        });

        this.$dropdown.show();
        
        const pos = this.$textarea.position();
        
        // Position above if in custom chat room (as input is at bottom), else below
        if (this.$textarea.closest('.ess-chat-container').length > 0) {
            this.$dropdown.css({
                top: pos.top - this.$dropdown.outerHeight() - 5,
                left: pos.left,
                width: this.$textarea.outerWidth()
            });
        } else {
            this.$dropdown.css({
                top: pos.top + this.$textarea.outerHeight(),
                left: pos.left,
                width: this.$textarea.outerWidth()
            });
        }
    }

    _hideDropdown() {
        if (this.$dropdown) {
            this.$dropdown.remove();
            this.$dropdown = null;
        }
        this.mentionStartIndex = -1;
    }

    _onKeydown(e) {
        if (!this.$dropdown) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.activeIndex = (this.activeIndex + 1) % this.suggestions.length;
            this._updateActiveItem();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.activeIndex = (this.activeIndex - 1 + this.suggestions.length) % this.suggestions.length;
            this._updateActiveItem();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            this._selectUser(this.suggestions[this.activeIndex]);
        } else if (e.key === 'Escape') {
            this._hideDropdown();
        }
    }

    _updateActiveItem() {
        this.$dropdown.find('.ess-mention-item').removeClass('active');
        this.$dropdown.find('.ess-mention-item').eq(this.activeIndex).addClass('active');
    }

    _selectUser(user) {
        const text = this.$textarea.val();
        const before = text.substring(0, this.mentionStartIndex);
        const after = text.substring(this.cursorPos);
        
        const mentionText = `@${user.name} `;
        this.$textarea.val(before + mentionText + after);
        
        // Track the mentioned partner
        this.mentionedPartners.push({
            id: user.id,
            name: user.name
        });

        this._hideDropdown();
        this.$textarea.focus();
        
        // Set cursor position after the inserted mention
        const newPos = before.length + mentionText.length;
        this.$textarea[0].setSelectionRange(newPos, newPos);
        
        // Trigger input event to resize textarea or notify form
        this.$textarea.trigger('input');
        this.$textarea.trigger('change');
    }

    getMentionedPartnerIds() {
        // Only return partners whose names are still in the text
        const text = this.$textarea.val();
        const validIds = [];
        this.mentionedPartners.forEach(p => {
            if (text.includes(`@${p.name}`)) {
                validIds.push(p.id);
            }
        });
        return [...new Set(validIds)];
    }
}

// Widget for Custom Chat Room
publicWidget.registry.PortalChatMentions = publicWidget.Widget.extend({
    selector: '#ess-chat-input',
    
    start: function () {
        this._super.apply(this, arguments);
        const textarea = this.el;
        if (textarea) {
            const historyEl = document.getElementById('ess-chat-history');
            const channelId = historyEl ? historyEl.getAttribute('data-channel-id') : null;
            
            if (channelId) {
                this.mentionAutocomplete = new MentionAutocomplete(textarea, 'discuss.channel', channelId);
                $(textarea).data('mentionAutocomplete', this.mentionAutocomplete);
            } else {
                console.error("MentionAutocomplete: Could not find channel ID.");
            }
        }
    }
});

function setupShadowMentions(shadow, chatterEl) {
    const textarea = shadow.querySelector('.o-mail-Composer-input');
    if (!textarea) {
        // Textarea might be conditionally rendered later
        setTimeout(() => setupShadowMentions(shadow, chatterEl), 500);
        return;
    }
    
    const resModel = chatterEl.getAttribute('data-res_model');
    const resId = chatterEl.getAttribute('data-res_id');
    
    const mentionAutocomplete = new MentionAutocomplete(textarea, resModel, resId);
    
    const form = shadow.querySelector('.o-mail-Composer');
    if (form) {
        // Since Odoo 19 composer uses its own submission, we intercept the Send button click instead
        const sendBtn = shadow.querySelector('.o-mail-Composer-send');
        if (sendBtn) {
            sendBtn.addEventListener('click', function (e) {
                const pIds = mentionAutocomplete.getMentionedPartnerIds();
                if (pIds.length) {
                    // Inject into body before it is sent?
                    // Actually, modifying composer text is hard because it's managed by OWL state.
                    // But we already did a backend workaround! We just need to trigger a backend call to pass partner_ids?
                    // Wait, standard chatter doesn't submit standard form, it does rpc!
                    // If we can't inject partner_ids to rpc directly, the backend Python message_post automatically parses the body!
                    // We ALREADY parse @Name in python in project.task message_post! So we don't even need to inject partner_ids here!
                    console.log("Mentioned partners:", pIds);
                }
            });
        }
    }
    
    const style = document.createElement('style');
    style.textContent = `
        .ess-mention-dropdown {
            position: absolute;
            z-index: 1050;
            max-height: 200px;
            overflow-y: auto;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            margin-top: 4px;
            background-color: white;
            padding-left: 0;
            list-style: none;
        }
        .ess-mention-item {
            cursor: pointer;
            padding: 8px 12px;
            border-bottom: 1px solid #f1f5f9;
        }
        .ess-mention-item:last-child {
            border-bottom: none;
        }
        .ess-mention-item:hover, .ess-mention-item.active {
            background-color: #f8f9fa;
            color: #000;
        }
    `;
    shadow.appendChild(style);
}

// Widget for standard Portal Chatter
publicWidget.registry.PortalChatterMentions = publicWidget.Widget.extend({
    selector: '.o_portal_chatter',
    
    start: function () {
        this._super.apply(this, arguments);
        
        const chatterEl = this.el;
        
        const checkShadow = () => {
            const chatterRoot = document.getElementById('chatterRoot');
            if (chatterRoot && chatterRoot.shadowRoot) {
                setupShadowMentions(chatterRoot.shadowRoot, chatterEl);
            } else {
                setTimeout(checkShadow, 200);
            }
        };
        checkShadow();
    }
});

export default MentionAutocomplete;

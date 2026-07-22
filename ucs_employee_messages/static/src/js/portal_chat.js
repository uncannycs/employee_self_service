/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.PortalChat = publicWidget.Widget.extend({
    selector: '.ess-chat-container',
    events: {
        'submit #ess-chat-form': '_onSendMessage',
        'keydown #ess-chat-input': '_onKeydown',
    },

    init: function () {
        this._super.apply(this, arguments);
        this.lastMessageId = 0;
        this.pollInterval = null;
    },

    start: function () {
        const historyEl = this.el.querySelector('#ess-chat-history');
        if (historyEl) {
            this.channelId = historyEl.dataset.channelId;
            this.partnerId = historyEl.dataset.partnerId;
            this._fetchMessages();
            
            // Poll every 5 seconds for new messages
            this.pollInterval = setInterval(this._fetchMessages.bind(this), 5000);
        }
        return this._super.apply(this, arguments);
    },
    
    destroy: function () {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
        this._super.apply(this, arguments);
    },

    _fetchMessages: function () {
        if (!this.channelId) return;
        
        rpc(`/my/chats/${this.channelId}/messages`, {
            last_id: this.lastMessageId
        }).then((data) => {
            if (data.error) {
                console.error(data.error);
                return;
            }
            // Always remove loading indicator on first successful fetch
            const historyEl = this.el.querySelector('#ess-chat-history');
            const loadingEl = historyEl && historyEl.querySelector('.ess-chat-loading');
            if (loadingEl) {
                loadingEl.remove();
            }

            if (data.messages && data.messages.length > 0) {
                this._renderMessages(data.messages);
            }
        });
    },

    _renderMessages: function (messages) {
        const historyEl = this.el.querySelector('#ess-chat-history');

        messages.forEach((msg) => {
            if (msg.id > this.lastMessageId) {
                this.lastMessageId = msg.id;
            }

            const isSelf = msg.is_self;
            const msgClass = isSelf ? 'ess-chat-message-self' : 'ess-chat-message-other';
            
            // Convert newline to br for display
            const formattedBody = msg.body; // body is already html from odoo message_post
            
            let html = `
                <div class="ess-chat-message ${msgClass}" data-message-id="${msg.id}">
                    <div class="ess-chat-meta">
                        ${!isSelf ? `<span class="ess-chat-author">${msg.author_name}</span>` : ''}
                        <span class="ess-chat-time">${msg.date}</span>
                    </div>
                    <div class="ess-chat-bubble">
                        ${formattedBody}
                    </div>
                </div>
            `;
            
            historyEl.insertAdjacentHTML('beforeend', html);
        });
        
        // Auto scroll to bottom
        historyEl.scrollTop = historyEl.scrollHeight;
    },

    _onKeydown: function (ev) {
        if (ev.key === 'Enter' && !ev.shiftKey) {
            ev.preventDefault();
            this.el.querySelector('#ess-chat-form').dispatchEvent(new Event('submit', { cancelable: true }));
        }
    },

    _onSendMessage: function (ev) {
        ev.preventDefault();
        const inputEl = this.el.querySelector('#ess-chat-input');
        const body = inputEl.value;
        const btn = this.el.querySelector('button[type="submit"]');

        if (!body.trim()) return;

        inputEl.disabled = true;
        btn.disabled = true;

        let partnerIds = [];
        const autocomplete = $(inputEl).data('mentionAutocomplete');
        if (autocomplete) {
            partnerIds = autocomplete.getMentionedPartnerIds();
        }

        rpc(`/my/chats/${this.channelId}/send`, {
            body: body,
            partner_ids: partnerIds
        }).then((data) => {
            inputEl.disabled = false;
            btn.disabled = false;
            
            if (data.success) {
                inputEl.value = '';
                // Immediately fetch messages to show the one we just sent
                this._fetchMessages();
            } else if (data.error) {
                alert(data.error);
            }
            
            inputEl.focus();
        }).catch(() => {
            inputEl.disabled = false;
            btn.disabled = false;
        });
    }
});

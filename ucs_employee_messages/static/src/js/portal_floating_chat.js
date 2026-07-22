/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";
import MentionAutocomplete from "./portal_mentions";

publicWidget.registry.PortalFloatingChat = publicWidget.Widget.extend({
    selector: '#ess-floating-chat-app',
    events: {
        'click #ess-chat-fab': '_onToggleSidebar',
        'click #ess-chat-sidebar-close': '_onCloseSidebar',
        'click #ess-chat-sidebar-back': '_onBackToChannels',
        'click .ess-chat-channel-item': '_onChannelClick',
        'submit #ess-chat-form': '_onSendMessage',
        'keydown #ess-chat-input': '_onKeydown',
    },

    init: function () {
        this._super.apply(this, arguments);
        this.isOpen = false;
        this.currentChannelId = null;
        this.currentPartnerId = null; // We can get this from session, or it's returned by messages
        this.lastMessageId = 0;
        this.pollInterval = null;
        
        this.lastMaxId = 0;
        this.isPollingGlobal = false;
        this.globalPollInterval = null;
    },

    start: function () {
        this.$sidebar = this.$('#ess-chat-sidebar');
        this.$channelsContainer = this.$('#ess-chat-sidebar-channels');
        this.$channelList = this.$('#ess-chat-channel-list');
        this.$roomContainer = this.$('#ess-chat-sidebar-room');
        this.$history = this.$('#ess-chat-history');
        this.$input = this.$('#ess-chat-input');
        this.$title = this.$('#ess-chat-sidebar-title');
        this.$backBtn = this.$('#ess-chat-sidebar-back');
        this.$badge = this.$('#ess-chat-fab-badge');

        // Start global polling for unread badges and push notifications every 10 seconds
        this.globalPollInterval = setInterval(this._pollGlobalNotifications.bind(this), 10000);
        this._pollGlobalNotifications();
        
        // Also fetch the channel list initially
        this._fetchChannels();
        
        return this._super.apply(this, arguments);
    },

    destroy: function () {
        if (this.globalPollInterval) {
            clearInterval(this.globalPollInterval);
        }
        this._stopPolling();
        this._super.apply(this, arguments);
    },

    async _pollGlobalNotifications() {
        if (this.isPollingGlobal) return;
        this.isPollingGlobal = true;
        
        try {
            const data = await rpc('/my/chats/unread', {
                last_id: this.lastMaxId
            });
            
            this.isPollingGlobal = false;
            
            if (data.error) {
                if (this.globalPollInterval) clearInterval(this.globalPollInterval);
                return;
            }
            
            if (data.max_id > this.lastMaxId) {
                this.lastMaxId = data.max_id;
            }
            
            // Update global FAB badge
            if (data.total_unread_chats !== undefined) {
                const fabBadge = document.getElementById('ess-chat-fab-badge');
                if (fabBadge) {
                    if (data.total_unread_chats > 0) {
                        fabBadge.textContent = data.total_unread_chats;
                        fabBadge.classList.remove('d-none');
                    } else {
                        fabBadge.classList.add('d-none');
                    }
                }
            }
            
            // If sidebar is open and showing channel list, update the badges
            if (this.isOpen && !this.currentChannelId && data.unread_counts) {
                for (const [channelId, count] of Object.entries(data.unread_counts)) {
                    const $item = this.$channelList.find(`[data-id="${channelId}"]`);
                    if ($item.length) {
                        let $badge = $item.find('.badge');
                        if (count > 0) {
                            if ($badge.length) {
                                $badge.text(count);
                            } else {
                                $item.find('.fa-chevron-right').before(`<span class="badge text-bg-danger rounded-pill mr-3">${count}</span>`);
                            }
                        } else {
                            if ($badge.length) $badge.remove();
                        }
                    }
                }
            }
            
            if (data.messages && data.messages.length > 0) {
                this._showPushNotifications(data.messages);
            }
            
        } catch(e) {
            this.isPollingGlobal = false;
        }
    },
    
    _showPushNotifications(messages) {
        // Play notification sound
        try {
            const audio = new Audio('/mail/static/src/audio/ting.mp3');
            audio.play().catch(e => console.log("Audio play failed:", e));
        } catch (e) {
            console.log("Audio initialization failed:", e);
        }
        
        const container = document.getElementById('ess-global-toast-container');
        
        messages.forEach(msg => {
            // Decode HTML entities and strip tags
            const textarea = document.createElement("textarea");
            textarea.innerHTML = msg.body || "";
            let decoded = textarea.value;
            
            // Second pass for double escaping
            textarea.innerHTML = decoded;
            decoded = textarea.value;
            
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = decoded;
            let textBody = tempDiv.textContent || tempDiv.innerText || "";
            if (textBody.length > 60) {
                textBody = textBody.substring(0, 60) + '...';
            }
            
            // Show Toast (In-browser popup)
            if (container) {
                const toastId = `ess-toast-${msg.id}`;
                const html = `
                    <div id="${toastId}" class="toast show mb-2" role="alert" aria-live="assertive" aria-atomic="true" style="min-width: 300px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); cursor: pointer;">
                        <div class="toast-header" style="background: linear-gradient(135deg, #cffafe, #a5f3fc); color: #0891b2; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom: none;">
                            <i class="fa fa-comments mr-2"></i>
                            <strong class="mr-auto text-dark">${msg.channel_name}</strong>
                            <small class="text-muted ml-3">Just now</small>
                            <button type="button" class="ml-2 mb-1 close ess-toast-close" data-dismiss="toast" aria-label="Close" data-target="#${toastId}">
                                <span aria-hidden="true">&times;</span>
                            </button>
                        </div>
                        <div class="toast-body bg-white" style="border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;" data-channel-id="${msg.channel_id}">
                            <strong>${msg.author_name}:</strong> <span class="text-muted">${textBody}</span>
                        </div>
                    </div>
                `;
                
                const $toast = $(html);
                
                $toast.on('click', (e) => {
                    if ($(e.target).closest('.ess-toast-close').length) {
                        $toast.removeClass('show');
                        setTimeout(() => $toast.remove(), 300);
                        return;
                    }
                    
                    // User clicked on the toast body/header
                    if (!this.isOpen) {
                        this._onToggleSidebar();
                    }
                    
                    // Programmatically click the channel
                    setTimeout(() => {
                        const $channel = this.$channelList.find(`[data-id="${msg.channel_id}"]`);
                        if ($channel.length) {
                            $channel.click();
                        } else {
                            this.currentChannelId = msg.channel_id;
                            this._fetchChannels().then(() => {
                                this.$channelList.find(`[data-id="${msg.channel_id}"]`).click();
                            });
                        }
                    }, 300);
                    
                    $toast.removeClass('show');
                    setTimeout(() => $toast.remove(), 300);
                });
                
                $(container).append($toast);
                
                setTimeout(() => {
                    $toast.removeClass('show');
                    setTimeout(() => $toast.remove(), 300);
                }, 6000);
            }
            
            // Show desktop push notification
            if ("Notification" in window && Notification.permission === "granted") {
                const pushNotif = new Notification(msg.channel_name, {
                    body: `${msg.author_name}: ${textBody}`,
                    icon: '/web/image/res.company/1/logo'
                });
                
                pushNotif.onclick = () => {
                    window.focus();
                    
                    // Open the sidebar if closed
                    if (!this.isOpen) {
                        this._onToggleSidebar();
                    }
                    
                    // Programmatically click the channel to open it
                    setTimeout(() => {
                        const $channel = this.$channelList.find(`[data-id="${msg.channel_id}"]`);
                        if ($channel.length) {
                            $channel.click();
                        } else {
                            this.currentChannelId = msg.channel_id;
                            this._fetchChannels().then(() => {
                                this.$channelList.find(`[data-id="${msg.channel_id}"]`).click();
                            });
                        }
                    }, 300);
                };
            }
        });
    },

    _onToggleSidebar: function (e) {
        if (e) e.preventDefault();
        
        // Request Notification permission on user gesture if not yet decided
        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
        }
        
        this.isOpen = !this.isOpen;
        if (this.isOpen) {
            this.$sidebar.removeClass('ess-sidebar-hidden');
            if (!this.currentChannelId) {
                this._fetchChannels();
            } else {
                this._scrollToBottom();
            }
        } else {
            this.$sidebar.addClass('ess-sidebar-hidden');
        }
    },

    _onCloseSidebar: function (e) {
        if (e) e.preventDefault();
        this.isOpen = false;
        this.$sidebar.addClass('ess-sidebar-hidden');
    },

    _onBackToChannels: function (e) {
        if (e) e.preventDefault();
        this.currentChannelId = null;
        this._stopPolling();
        
        this.$roomContainer.addClass('d-none');
        this.$channelsContainer.removeClass('d-none');
        this.$backBtn.addClass('d-none');
        this.$title.html('<i class="fa fa-comments mr-2"></i> My Messages');
        
        this._fetchChannels();
    },

    async _fetchChannels() {
        try {
            const result = await rpc('/my/chats/api/channels', {});
            const channels = result.channels || [];
            
            let totalUnread = 0;
            this.$channelList.empty();
            this.$channelsContainer.find('.ess-chat-loading').addClass('d-none');
            
            if (channels.length === 0) {
                this.$channelList.append(`
                    <div class="p-4 text-center text-muted">
                        <i class="fa fa-info-circle fa-2x mb-2"></i>
                        <p>No active conversations found.</p>
                    </div>
                `);
            } else {
                channels.forEach(ch => {
                    totalUnread += ch.unread_count;
                    const badge = ch.unread_count > 0 ? `<span class="badge bg-danger rounded-pill">${ch.unread_count}</span>` : '';
                    
                    const $item = $(`
                        <div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center py-3 ess-chat-channel-item" data-id="${ch.id}" data-name="${ch.name}">
                            <div class="d-flex align-items-center">
                                <div class="ess-channel-icon mr-3">
                                    <i class="fa fa-hashtag fa-lg"></i>
                                </div>
                                <div>
                                    <h6 class="mb-1 text-dark font-weight-bold">${ch.name}</h6>
                                    <small class="text-muted">${ch.member_count} Members</small>
                                </div>
                            </div>
                            <div class="d-flex align-items-center gap-2">
                                ${badge}
                                <i class="fa fa-chevron-right text-muted"></i>
                            </div>
                        </div>
                    `);
                    this.$channelList.append($item);
                });
            }
            
            // Update global FAB badge
            const fabBadge = document.getElementById('ess-chat-fab-badge');
            if (fabBadge) {
                if (totalUnread > 0) {
                    fabBadge.textContent = totalUnread;
                    fabBadge.classList.remove('d-none');
                } else {
                    fabBadge.classList.add('d-none');
                }
            }
            
        } catch (e) {
            console.error("Failed to fetch channels:", e);
        }
    },

    async _onChannelClick(e) {
        const $target = $(e.currentTarget);
        this.currentChannelId = $target.data('id');
        const channelName = $target.data('name');
        
        this.$channelsContainer.addClass('d-none');
        this.$roomContainer.removeClass('d-none');
        this.$backBtn.removeClass('d-none');
        this.currentChannelName = $target.find('h6').text().trim();
        
        // Hide input form if channel is a Task Discussion
        const $inputArea = this.$('#ess-chat-form').closest('.border-top');
        if (this.currentChannelName.startsWith('Task Discussion:')) {
            $inputArea.hide();
        } else {
            $inputArea.show();
        }
        
        this.$title.html(`<i class="fa fa-hashtag mr-2"></i> ${this.currentChannelName}`);
        
        this.$history.empty();
        this.$history.append(`
            <div class="text-center text-muted p-4 ess-chat-loading">
                <i class="fa fa-spinner fa-spin fa-2x mb-2"></i>
                <p>Loading messages...</p>
            </div>
        `);
        
        this.lastMessageId = 0;
        
        // Mark as read immediately
        try {
            await rpc('/my/chats/api/mark_read', { channel_id: this.currentChannelId });
            this._fetchChannels(); // update badge
        } catch(e) {}
        
        await this._fetchMessages();
        
        // Expose channel id to the element so MentionAutocomplete can find it
        this.$history.attr('data-channel-id', this.currentChannelId);
        
        // Initialize MentionAutocomplete
        if (this.mentionAutocomplete) {
            this.mentionAutocomplete._hideDropdown();
        }
        this.mentionAutocomplete = new MentionAutocomplete(this.$input[0], 'discuss.channel', this.currentChannelId);
        this.$input.data('mentionAutocomplete', this.mentionAutocomplete);
        
        this._startPolling();
    },

    _startPolling() {
        this._stopPolling();
        this.pollInterval = setInterval(() => {
            if (this.currentChannelId && this.isOpen) {
                this._fetchMessages();
            }
        }, 5000);
    },

    _stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    },

    async _fetchMessages() {
        if (!this.currentChannelId) return;
        
        try {
            const result = await rpc(`/my/chats/${this.currentChannelId}/messages`, {
                last_id: this.lastMessageId
            });
            
            const messages = result.messages || [];
            if (messages.length > 0) {
                this.$history.find('.ess-chat-loading').remove();
                
                let isScrolledToBottom = false;
                if (this.$history[0]) {
                    isScrolledToBottom = this.$history[0].scrollHeight - this.$history[0].scrollTop <= this.$history[0].clientHeight + 10;
                }
                
                messages.forEach(msg => {
                    if (msg.id > this.lastMessageId) {
                        this.lastMessageId = msg.id;
                    }
                    this._appendMessage(msg);
                });
                
                // If it's the first load or user was at bottom, scroll down
                if (isScrolledToBottom || messages.length === result.messages.length) {
                    this._scrollToBottom();
                }
                
                // Mark read since we fetched new messages
                rpc('/my/chats/api/mark_read', { channel_id: this.currentChannelId });
            } else if (this.lastMessageId === 0) {
                this.$history.find('.ess-chat-loading').remove();
                if (this.$history.children().length === 0) {
                    this.$history.append(`
                        <div class="text-center text-muted p-4 ess-chat-empty">
                            <i class="fa fa-comments-o fa-3x mb-3" style="opacity: 0.5;"></i>
                            <h6>No messages yet</h6>
                            <p class="small">Send a message to start the conversation.</p>
                        </div>
                    `);
                }
            }
        } catch (e) {
            console.error("Failed to fetch messages:", e);
        }
    },

    _appendMessage(msg) {
        this.$history.find('.ess-chat-empty').remove();
        
        const isSelf = msg.is_self;
        const alignClass = isSelf ? 'justify-content-end' : 'justify-content-start';
        const bgClass = isSelf ? 'ess-msg-self' : 'ess-msg-other';
        const authorInfo = isSelf ? '' : `<small class="text-muted mb-1 d-block font-weight-bold" style="font-size: 0.75rem;">${msg.author_name} &bull; ${msg.date}</small>`;
        const dateSelf = isSelf ? `<small class="text-muted mb-1 d-block text-right" style="font-size: 0.7rem;">${msg.date}</small>` : '';

        // Add task/chatter specific styles if it has a custom message type
        let extraStyles = '';
        if (msg.message_type === 'notification') {
            extraStyles = 'background-color: #f8f9fa; border: 1px solid #e2e8f0; font-style: italic; color: #64748b; font-size: 0.85rem;';
        }

        // Decode HTML entities and strip tags
        const textarea = document.createElement("textarea");
        textarea.innerHTML = msg.body || "";
        let decoded = textarea.value;
        
        // Second pass for double escaping
        textarea.innerHTML = decoded;
        decoded = textarea.value;
        
        // Preserve line breaks
        decoded = decoded.replace(/<br\s*\/?>/gi, '\n');
        decoded = decoded.replace(/<\/p>/gi, '\n');
        
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = decoded;
        let cleanBody = tempDiv.textContent || tempDiv.innerText || "";
        cleanBody = cleanBody.trim().replace(/\n/g, '<br>');

        const bubbleHTML = `
            <div class="d-flex w-100 ${alignClass} mb-3" data-message-id="${msg.id}">
                <div style="max-width: 85%;">
                    ${dateSelf}
                    ${authorInfo}
                    <div class="p-3 shadow-sm ${bgClass}" style="border-radius: 16px; word-wrap: break-word; ${extraStyles}">
                        ${cleanBody}
                    </div>
                </div>
            </div>
        `;
        
        this.$history.append(bubbleHTML);
    },

    _scrollToBottom() {
        if (this.$history.length) {
            this.$history.scrollTop(this.$history[0].scrollHeight);
        }
    },

    _onKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.$('#ess-chat-form').trigger('submit');
        }
    },

    async _onSendMessage(e) {
        e.preventDefault();
        if (!this.currentChannelId) return;
        
        const text = this.$input.val().trim();
        if (!text) return;

        // Try to get mention IDs if the mention widget is attached
        let pIds = [];
        const mentionWidget = this.$input.data('mentionAutocomplete');
        if (mentionWidget) {
            pIds = mentionWidget.getMentionedPartnerIds();
        }

        this.$input.val('');
        this.$input.prop('disabled', true);
        
        try {
            await rpc(`/my/chats/${this.currentChannelId}/send`, {
                body: text,
                partner_ids: pIds.join(',')
            });
            
            // Re-fetch immediately
            await this._fetchMessages();
        } catch (e) {
            console.error("Failed to send message:", e);
            alert("Failed to send message. Please try again.");
            this.$input.val(text);
        } finally {
            this.$input.prop('disabled', false);
            this.$input.focus();
        }
    }
});

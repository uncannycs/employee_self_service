/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.PortalGlobalNotification = publicWidget.Widget.extend({
    selector: '#wrapwrap', // Attaches to the main wrapper of all portal pages
    events: {
        'click .ess-toast-close': '_onCloseToast',
    },

    init: function () {
        this._super.apply(this, arguments);
        this.lastMaxId = 0;
        this.isPolling = false;
    },

    start: function () {
        // Request Notification permission for desktop push
        if ("Notification" in window && Notification.permission !== "denied" && Notification.permission !== "granted") {
            Notification.requestPermission();
        }
        
        // Only run if the user is logged in (which means they can access /my/chats)
        // We'll just try to poll, if it returns 403/Unauthorized we stop
        this._pollUnreadMessages();
        this.pollInterval = setInterval(this._pollUnreadMessages.bind(this), 10000); // Check every 10 seconds
        return this._super.apply(this, arguments);
    },

    destroy: function () {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
        this._super.apply(this, arguments);
    },

    _pollUnreadMessages: function () {
        if (this.isPolling) return;
        this.isPolling = true;

        rpc(`/my/chats/unread`, {
            last_id: this.lastMaxId
        }).then((data) => {
            this.isPolling = false;
            if (data.error) {
                // E.g., not logged in
                clearInterval(this.pollInterval);
                return;
            }

            if (data.max_id > this.lastMaxId) {
                this.lastMaxId = data.max_id;
            }
            
            // Update Dashboard Badge
            if (data.total_unread_chats !== undefined) {
                const dashBadge = document.getElementById('ess-dashboard-unread-badge');
                if (dashBadge) {
                    dashBadge.textContent = data.total_unread_chats;
                    if (data.total_unread_chats > 0) {
                        dashBadge.classList.remove('d-none');
                    } else {
                        dashBadge.classList.add('d-none');
                    }
                }
            }
            
            // Update Channel Badges
            if (data.unread_counts !== undefined) {
                for (const [channelId, count] of Object.entries(data.unread_counts)) {
                    const channelBadge = document.getElementById(`ess-channel-unread-badge-${channelId}`);
                    if (channelBadge) {
                        channelBadge.textContent = count;
                        if (count > 0) {
                            channelBadge.classList.remove('d-none');
                        } else {
                            channelBadge.classList.add('d-none');
                        }
                    }
                }
            }

            if (data.messages && data.messages.length > 0) {
                this._showToasts(data.messages);
            }
        }).catch(() => {
            this.isPolling = false;
        });
    },

    _showToasts: function (messages) {
        // Play notification sound
        try {
            const audio = new Audio('/mail/static/src/audio/ting.mp3');
            audio.play().catch(e => console.log("Audio play failed:", e));
        } catch (e) {
            console.log("Audio initialization failed:", e);
        }

        const container = document.getElementById('ess-global-toast-container');
        // We still process notifications even if container is missing (for desktop push)

        messages.forEach(msg => {
            // Strip HTML from msg.body for summary, or just show it if it's safe. 
            // Odoo msg.body is HTML, we'll extract text or just let it render safely.
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = msg.body;
            let textBody = tempDiv.textContent || tempDiv.innerText || "";
            if (textBody.length > 60) {
                textBody = textBody.substring(0, 60) + '...';
            }

            const toastId = `ess-toast-${msg.id}`;
            const html = `
                <div id="${toastId}" class="toast show mb-2" role="alert" aria-live="assertive" aria-atomic="true" style="min-width: 300px; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);">
                    <div class="toast-header" style="background: linear-gradient(135deg, #cffafe, #a5f3fc); color: #0891b2; border-top-left-radius: 12px; border-top-right-radius: 12px; border-bottom: none;">
                        <i class="fa fa-comments mr-2"></i>
                        <strong class="mr-auto text-dark">${msg.channel_name}</strong>
                        <small class="text-muted ml-3">Just now</small>
                        <button type="button" class="ml-2 mb-1 close ess-toast-close" data-dismiss="toast" aria-label="Close" data-target="#${toastId}">
                            <span aria-hidden="true">&times;</span>
                        </button>
                    </div>
                    <a href="/my/chats/${msg.channel_id}" class="text-decoration-none text-dark d-block">
                        <div class="toast-body bg-white" style="border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;">
                            <strong>${msg.author_name}:</strong> <span class="text-muted">${textBody}</span>
                        </div>
                    </a>
                </div>
            `;
            
            if (container) {
                container.insertAdjacentHTML('beforeend', html);
                
                // Auto remove after 6 seconds
                setTimeout(() => {
                    const toastEl = document.getElementById(toastId);
                    if (toastEl) {
                        toastEl.classList.remove('show');
                        setTimeout(() => toastEl.remove(), 300);
                    }
                }, 6000);
            }
            
            // Show desktop push notification
            if ("Notification" in window && Notification.permission === "granted") {
                const pushNotif = new Notification(msg.channel_name, {
                    body: `${msg.author_name}: ${textBody}`,
                    icon: '/web/image/res.company/1/logo'
                });
                
                pushNotif.onclick = function () {
                    window.focus();
                    window.location.href = `/my/chats/${msg.channel_id}`;
                };
            }
        });

    },

    _onCloseToast: function (ev) {
        const targetId = ev.currentTarget.dataset.target;
        const toastEl = this.el.querySelector(targetId);
        if (toastEl) {
            toastEl.classList.remove('show');
            setTimeout(() => toastEl.remove(), 300);
        }
    }
});

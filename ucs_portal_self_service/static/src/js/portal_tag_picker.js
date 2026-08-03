/* ESS Portal - Universal Odoo Backend-Style Tag Picker Component */
(function() {
    function setupTagPickers() {
        document.querySelectorAll('.ess-tag-picker-container').forEach(function(container) {
            if (container.dataset.bound) return;
            container.dataset.bound = "true";

            var triggerBox = container.querySelector('.ess-tag-trigger-box');
            var dropdown = container.querySelector('.ess-tag-dropdown-menu');
            var hiddenSelect = container.querySelector('.ess-hidden-tags-select');
            var badgeList = container.querySelector('.ess-tag-badge-list');
            var searchInput = container.querySelector('.ess-tag-search-input');
            var optionItems = container.querySelectorAll('.ess-tag-option-item');

            if (!triggerBox || !dropdown || !hiddenSelect) return;

            function syncUI() {
                var selectedOpts = Array.from(hiddenSelect.options).filter(function(o) { return o.selected; });
                badgeList.innerHTML = '';

                if (selectedOpts.length > 0) {
                    if (searchInput) searchInput.placeholder = '';
                    selectedOpts.forEach(function(opt) {
                        var tagId = opt.value;
                        var tagName = opt.getAttribute('data-name') || opt.text;
                        var tagStyle = opt.getAttribute('data-style') || 'background-color: #6c757d; color: white;';
                        
                        var pill = document.createElement('span');
                        pill.className = 'badge rounded-pill px-2 py-1 d-inline-flex align-items-center gap-1 ess-tag-pill';
                        pill.setAttribute('data-tag-id', tagId);
                        pill.style.cssText = tagStyle + ' font-size: 0.8rem; font-weight: 500; margin-right: 4px; margin-bottom: 2px;';
                        pill.innerHTML = '<span>' + tagName + '</span><i class="fa fa-times ms-1 ess-rem-btn" style="cursor:pointer; margin-left: 4px; opacity: 0.85;"></i>';
                        
                        pill.querySelector('.ess-rem-btn').addEventListener('click', function(ev) {
                            ev.stopPropagation();
                            opt.selected = false;
                            syncUI();
                        });
                        badgeList.appendChild(pill);
                    });
                } else {
                    if (searchInput) searchInput.placeholder = 'Select tags...';
                }

                optionItems.forEach(function(item) {
                    var tid = item.getAttribute('data-tag-id');
                    var isSelected = selectedOpts.some(function(o) { return o.value == tid; });
                    var checkMark = item.querySelector('.ess-check-mark');
                    if (checkMark) {
                        if (isSelected) {
                            checkMark.classList.remove('d-none');
                            item.style.background = '#f0fdf4';
                        } else {
                            checkMark.classList.add('d-none');
                            item.style.background = 'transparent';
                        }
                    }
                });
            }

            triggerBox.addEventListener('click', function(e) {
                e.stopPropagation();
                document.querySelectorAll('.ess-tag-dropdown-menu').forEach(function(d) { 
                    if (d !== dropdown) d.style.display = 'none'; 
                });
                dropdown.style.display = 'block';
                if (searchInput) searchInput.focus();
            });

            if (searchInput) {
                searchInput.addEventListener('input', function(e) {
                    dropdown.style.display = 'block';
                    var q = e.target.value.toLowerCase().trim();
                    var matchCount = 0;
                    optionItems.forEach(function(item) {
                        var name = (item.getAttribute('data-name') || '').toLowerCase();
                        if (q === '' || name.indexOf(q) !== -1) {
                            item.style.setProperty('display', 'flex', 'important');
                            matchCount++;
                        } else {
                            item.style.setProperty('display', 'none', 'important');
                        }
                    });
                    var noTagsMsg = container.querySelector('.ess-no-tags-found');
                    if (noTagsMsg) {
                        if (matchCount === 0 && q !== '') {
                            noTagsMsg.classList.remove('d-none');
                        } else {
                            noTagsMsg.classList.add('d-none');
                        }
                    }
                });

                searchInput.addEventListener('keydown', function(e) {
                    if (e.key === 'Backspace' && searchInput.value === '') {
                        var selectedOpts = Array.from(hiddenSelect.options).filter(function(o) { return o.selected; });
                        if (selectedOpts.length > 0) {
                            var lastOpt = selectedOpts[selectedOpts.length - 1];
                            lastOpt.selected = false;
                            syncUI();
                        }
                    }
                });
            }

            optionItems.forEach(function(item) {
                item.addEventListener('click', function(e) {
                    e.stopPropagation();
                    var tid = this.getAttribute('data-tag-id');
                    Array.from(hiddenSelect.options).forEach(function(o) {
                        if (o.value == tid) {
                            o.selected = !o.selected;
                        }
                    });
                    if (searchInput) {
                        searchInput.value = '';
                        optionItems.forEach(function(it) { it.style.setProperty('display', 'flex', 'important'); });
                        var noTagsMsg = container.querySelector('.ess-no-tags-found');
                        if (noTagsMsg) noTagsMsg.classList.add('d-none');
                        searchInput.focus();
                    }
                    syncUI();
                });
            });

            document.addEventListener('click', function(e) {
                if (!container.contains(e.target)) {
                    dropdown.style.display = 'none';
                }
            });

            badgeList.querySelectorAll('.ess-remove-tag-icon').forEach(function(icon) {
                icon.addEventListener('click', function(ev) {
                    ev.stopPropagation();
                    var pill = icon.closest('.ess-tag-pill');
                    var tid = pill ? pill.getAttribute('data-tag-id') : null;
                    if (tid) {
                        Array.from(hiddenSelect.options).forEach(function(o) {
                            if (o.value == tid) o.selected = false;
                        });
                        syncUI();
                    }
                });
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupTagPickers);
    } else {
        setupTagPickers();
    }
    
    document.addEventListener('shown.bs.modal', setupTagPickers);
})();

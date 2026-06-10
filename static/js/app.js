let currentUser = 'skekare@salesforce.com';
let modalCallback = null;
let modifyTimecardId = null;

function getCurrentUser() {
    return document.getElementById('user-switcher').value;
}

function onUserSwitch() {
    currentUser = getCurrentUser();
    const activeTab = document.querySelector('.tab-content.active')?.id?.replace('tab-', '');
    if (activeTab) loadTab(activeTab);
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.add('active');
    document.querySelector(`.tab-btn[data-tab="${tabName}"]`)?.classList.add('active');
    loadTab(tabName);
}

function loadTab(tabName) {
    if (tabName === 'dashboard') loadDashboard();
    if (tabName === 'timecards') loadTimecards();
    if (tabName === 'projects') loadProjects();
    if (tabName === 'notifications') loadNotifications();
}

// ─── DASHBOARD ───────────────────────────────────────────────────────────────

async function loadDashboard() {
    const [consultants, tcs, notifs] = await Promise.all([
        fetch('/api/certinia/consultants').then(r => r.json()),
        fetch('/api/timecards').then(r => r.json()),
        fetch(`/api/notifications?email=${getCurrentUser()}`).then(r => r.json()),
    ]);

    const pending = tcs.filter(t => t.status === 'SUBMITTED').length;
    const approved = tcs.filter(t => t.status === 'APPROVED').length;
    document.getElementById('stat-pending').textContent = pending;
    document.getElementById('stat-approved').textContent = approved;
    document.getElementById('stat-notifs').textContent = notifs.length;
    updateBadge(notifs);

    // Team blocks grouped by employee
    const groups = {};
    consultants.forEach(c => {
        if (!groups[c.employee_name]) groups[c.employee_name] = { email: c.email, projects: [] };
        groups[c.employee_name].projects.push(c);
    });

    const container = document.getElementById('dashboard-team-blocks');
    container.innerHTML = Object.entries(groups).sort().map(([name, info]) => `
        <div class="employee-block">
            <div class="employee-block-header">
                <h4>${name}</h4>
                <span class="email">${info.email}</span>
            </div>
            <table class="mini-table">
                <thead><tr><th>Project ID</th><th>Project Name</th><th>Start</th><th>End</th><th>Allocated</th><th>Consumed</th></tr></thead>
                <tbody>
                    ${info.projects.map(p => `
                        <tr>
                            <td>${p.project_id}</td>
                            <td>${p.project_name}</td>
                            <td>${p.start_date}</td>
                            <td>${p.end_date}</td>
                            <td>${p.allocated_hours}h</td>
                            <td>${p.consumed_hours}h</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `).join('');
}

// ─── TIMECARDS ───────────────────────────────────────────────────────────────

async function loadTimecards() {
    const user = getCurrentUser();
    const isDM = user === 'skekare@salesforce.com';
    const tcs = await fetch(`/api/timecards?email=${user}`).then(r => r.json());

    const container = document.getElementById('timecards-container');

    if (tcs.length === 0) {
        container.innerHTML = '<div class="empty-state">No timecards yet. Run "Friday Timecard Generation" from the Actions tab.</div>';
        return;
    }

    container.innerHTML = tcs.map(tc => {
        const isOwner = tc.email === user;
        const canEdit = isOwner && (tc.status === 'DRAFT' || tc.status === 'REJECTED');

        let actions = '';
        if (isDM && tc.status === 'SUBMITTED') {
            actions = `
                <button class="btn btn-sm btn-success" onclick="approveTc(${tc.id})">Approve</button>
                <button class="btn btn-sm btn-danger" onclick="rejectTc(${tc.id})">Reject with Comment</button>
            `;
        } else if (isOwner && tc.status === 'DRAFT') {
            actions = `<button class="btn btn-sm btn-primary" onclick="submitTc(${tc.id})">Submit to DM</button>`;
        } else if (isOwner && tc.status === 'REJECTED') {
            actions = `<button class="btn btn-sm btn-primary" onclick="submitTc(${tc.id})">Resubmit to DM</button>`;
        }

        let commentBox = '';
        if (tc.status === 'REJECTED' && tc.dm_comment) {
            commentBox = `<div class="dm-comment-box"><strong>DM Comment:</strong> ${tc.dm_comment}</div>`;
        }

        let extraBanner = '';
        if (tc.has_extra && canEdit) {
            const extraItems = tc.entries.filter(e => e.is_extra);
            extraBanner = `
                <div class="extra-banner">
                    <strong>Extra work detected from Slack:</strong>
                    <ul>
                        ${extraItems.map(e => {
                            if (e.allocated_hours === 0) {
                                return `<li>${e.project_id} ${e.project_name}: <strong>${e.consumed_hours}h</strong> worked (not in your allocation)</li>`;
                            } else {
                                return `<li>${e.project_id} ${e.project_name}: <strong>${e.consumed_hours}h</strong> worked vs ${e.allocated_hours}h allocated (+${(e.consumed_hours - e.allocated_hours).toFixed(1)}h extra)</li>`;
                            }
                        }).join('')}
                    </ul>
                    <p class="muted">You can adjust hours below before submitting.</p>
                </div>
            `;
        }

        // Editable rows for DRAFT/REJECTED, read-only otherwise
        let tableBody = '';
        if (canEdit) {
            tableBody = tc.entries.map((e, i) => `
                <tr class="${e.is_extra ? 'extra-row' : ''}">
                    <td>${e.project_id}</td>
                    <td>${e.project_name}</td>
                    <td>${e.start_date}</td>
                    <td>${e.end_date}</td>
                    <td>${e.allocated_hours}h</td>
                    <td class="editable-cell">
                        <input type="number" class="hours-input" id="tc-${tc.id}-consumed-${i}"
                               value="${e.consumed_hours}" step="0.5" min="0"
                               onchange="markTimecardDirty(${tc.id})">
                    </td>
                    <td>${e.is_extra ? '<span class="extra-tag">EXTRA</span>' : '-'}</td>
                </tr>
            `).join('');
        } else {
            tableBody = tc.entries.map(e => `
                <tr class="${e.is_extra ? 'extra-row' : ''}">
                    <td>${e.project_id}</td>
                    <td>${e.project_name}</td>
                    <td>${e.start_date}</td>
                    <td>${e.end_date}</td>
                    <td>${e.allocated_hours}h</td>
                    <td>${e.consumed_hours}h</td>
                    <td>${e.is_extra ? '<span class="extra-tag">EXTRA</span>' : '-'}</td>
                </tr>
            `).join('');
        }

        let saveBtn = '';
        if (canEdit) {
            saveBtn = `<button class="btn btn-sm btn-secondary" id="save-btn-${tc.id}" style="display:none;" onclick="saveTimecardEdits(${tc.id})">Save Changes</button>`;
        }

        return `
            <div class="timecard-card status-${tc.status}">
                <div class="tc-header">
                    <h4>${tc.employee_name} <span class="muted">(${tc.email})</span></h4>
                    <span class="tc-status ${tc.status}">${tc.status}</span>
                </div>
                ${commentBox}
                ${extraBanner}
                <table class="tc-table">
                    <thead>
                        <tr><th>Project ID</th><th>Project Name</th><th>Start</th><th>End</th><th>Allocated</th><th>Consumed</th><th>Flag</th></tr>
                    </thead>
                    <tbody>${tableBody}</tbody>
                </table>
                <div class="tc-actions">${saveBtn} ${actions}</div>
            </div>
        `;
    }).join('');
}

function markTimecardDirty(tcId) {
    const btn = document.getElementById(`save-btn-${tcId}`);
    if (btn) btn.style.display = 'inline-block';
}

async function saveTimecardEdits(tcId) {
    const tc = await fetch(`/api/timecards/${tcId}`).then(r => r.json());
    const entries = tc.entries.map((e, i) => {
        const input = document.getElementById(`tc-${tcId}-consumed-${i}`);
        const consumed = input ? parseFloat(input.value) || 0 : e.consumed_hours;
        return {
            ...e,
            consumed_hours: consumed,
            is_extra: consumed > e.allocated_hours || e.allocated_hours === 0,
        };
    });

    const res = await fetch(`/api/timecards/${tcId}/modify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entries }),
    });
    const data = await res.json();
    showToast(data.message || 'Hours updated.');
    loadTimecards();
}

async function submitTc(id) {
    // First save any edits
    const tc = await fetch(`/api/timecards/${id}`).then(r => r.json());
    if (tc.status === 'DRAFT' || tc.status === 'REJECTED') {
        // Check if there are input fields (editable state)
        const firstInput = document.getElementById(`tc-${id}-consumed-0`);
        if (firstInput) {
            const entries = tc.entries.map((e, i) => {
                const input = document.getElementById(`tc-${id}-consumed-${i}`);
                const consumed = input ? parseFloat(input.value) || 0 : e.consumed_hours;
                return {
                    ...e,
                    consumed_hours: consumed,
                    is_extra: consumed > e.allocated_hours || e.allocated_hours === 0,
                };
            });
            await fetch(`/api/timecards/${id}/modify`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entries }),
            });
        }
    }

    const res = await fetch(`/api/timecards/${id}/submit`, { method: 'POST' });
    const data = await res.json();
    showToast(data.message || data.error);
    loadTimecards();
    loadDashboard();
}

async function approveTc(id) {
    const res = await fetch(`/api/timecards/${id}/approve`, { method: 'POST' });
    const data = await res.json();
    showToast(data.message || data.error);
    loadTimecards();
    loadDashboard();
}

function rejectTc(id) {
    document.getElementById('modal-title').textContent = 'Reject Timecard';
    document.getElementById('modal-desc').textContent = 'Provide a comment explaining what needs to change. The consultant will modify and resubmit.';
    document.getElementById('modal-textarea').value = '';
    document.getElementById('modal-submit-btn').textContent = 'Reject & Send Back';
    document.getElementById('modal-submit-btn').className = 'btn btn-danger';
    modalCallback = async () => {
        const comment = document.getElementById('modal-textarea').value.trim();
        if (!comment) { alert('Please provide a comment.'); return; }
        const res = await fetch(`/api/timecards/${id}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ comment }),
        });
        const data = await res.json();
        closeModal();
        showToast(data.message || data.error);
        loadTimecards();
        loadDashboard();
    };
    document.getElementById('modal-overlay').classList.add('active');
}

// ─── PROJECTS ────────────────────────────────────────────────────────────────

async function loadProjects() {
    const data = await fetch('/api/certinia/projects').then(r => r.json());
    document.getElementById('stat-projects').textContent = data.length;
    const container = document.getElementById('projects-container');
    container.innerHTML = data.map(p => `
        <div class="project-card">
            <span class="project-id">${p.project_id}</span>
            <div class="project-info">
                <h4>${p.project_name}</h4>
                <p>${p.start_date} to ${p.end_date} | Consultants: ${p.assigned_consultants}</p>
            </div>
            <div class="project-hours">
                <div class="consumed">${p.consumed_hours}h</div>
                <div class="total">of ${p.allocated_hours}h</div>
            </div>
        </div>
    `).join('');
}

// ─── NOTIFICATIONS ───────────────────────────────────────────────────────────

async function loadNotifications() {
    const user = getCurrentUser();
    const data = await fetch(`/api/notifications?email=${user}`).then(r => r.json());
    const container = document.getElementById('notifications-container');
    updateBadge(data);

    if (data.length === 0) {
        container.innerHTML = '<div class="empty-state">No notifications. Run a workflow from the Actions tab.</div>';
        return;
    }

    container.innerHTML = [...data].reverse().map(n => {
        let content = '';
        try {
            const payload = JSON.parse(n.message);
            content = renderNotifBlock(payload, n.type);
        } catch {
            content = `<div class="notif-content">${n.message}</div>`;
        }
        return `
            <div class="notif-item type-${n.type}">
                <div class="notif-meta">
                    <span>${n.type.replace(/_/g, ' ').toUpperCase()}</span>
                    <span>${n.timestamp}</span>
                </div>
                ${content}
            </div>
        `;
    }).join('');
}

function renderNotifBlock(payload, type) {
    if (payload.block_type === 'monday_allocation') {
        return `
            <div class="notif-content">
                <strong>Good morning ${payload.employee_name.split(' ')[0]}!</strong> Here's your week:
                <table class="mini-table" style="margin-top:0.5rem;">
                    <thead><tr><th>Project ID</th><th>Project</th><th>Start</th><th>End</th><th>Allocated</th><th>Consumed</th></tr></thead>
                    <tbody>${payload.projects.map(p => `
                        <tr><td>${p.project_id}</td><td>${p.project_name}</td><td>${p.start_date}</td><td>${p.end_date}</td><td>${p.allocated_hours}h</td><td>${p.consumed_hours}h</td></tr>
                    `).join('')}</tbody>
                </table>
            </div>
        `;
    }

    if (payload.block_type === 'monday_dm_overview') {
        return `
            <div class="notif-content">
                <strong>Good morning Shradha!</strong> Here's your team overview:
                ${payload.reportees.map(r => `
                    <div class="employee-block" style="margin-top:0.8rem;">
                        <div class="employee-block-header"><h4>${r.employee_name}</h4><span class="email">${r.email}</span></div>
                        <table class="mini-table">
                            <thead><tr><th>Project ID</th><th>Project</th><th>Start</th><th>End</th><th>Allocated</th><th>Consumed</th></tr></thead>
                            <tbody>${r.projects.map(p => `
                                <tr><td>${p.project_id}</td><td>${p.project_name}</td><td>${p.start_date}</td><td>${p.end_date}</td><td>${p.allocated_hours}h</td><td>${p.consumed_hours}h</td></tr>
                            `).join('')}</tbody>
                        </table>
                    </div>
                `).join('')}
            </div>
        `;
    }

    if (payload.block_type === 'friday_timecard') {
        let extraSection = '';
        if (payload.has_extra && payload.extra_summary) {
            extraSection = `
                <div class="extra-banner" style="margin:0.5rem 0;">
                    <strong>Extra work detected:</strong>
                    <ul>${payload.extra_summary.map(s => `<li>${s}</li>`).join('')}</ul>
                </div>
            `;
        }
        let entriesTable = '';
        if (payload.entries) {
            entriesTable = `
                <table class="mini-table" style="margin-top:0.5rem;">
                    <thead><tr><th>Project ID</th><th>Project</th><th>Start</th><th>End</th><th>Allocated</th><th>Consumed</th><th>Flag</th></tr></thead>
                    <tbody>${payload.entries.map(e => `
                        <tr class="${e.is_extra ? 'extra-row' : ''}">
                            <td>${e.project_id}</td><td>${e.project_name}</td><td>${e.start_date}</td><td>${e.end_date}</td>
                            <td>${e.allocated_hours}h</td><td>${e.consumed_hours}h</td>
                            <td>${e.is_extra ? '<span class="extra-tag">EXTRA</span>' : '-'}</td>
                        </tr>
                    `).join('')}</tbody>
                </table>
            `;
        }
        return `
            <div class="notif-content">
                <div style="margin-bottom:0.5rem;">${payload.message}</div>
                ${extraSection}
                ${entriesTable}
                <p class="muted" style="margin-top:0.5rem;">Go to Timecards tab to adjust hours and submit.</p>
            </div>
        `;
    }

    if (payload.block_type === 'timecard_status') {
        const color = payload.status === 'APPROVED' ? '#00b894' : '#0984e3';
        return `<div class="notif-content" style="color:${color}; font-weight:600;">${payload.message}</div>`;
    }

    if (payload.block_type === 'timecard_rejected') {
        return `
            <div class="notif-content">
                <div style="color:#e17055; font-weight:600; margin-bottom:0.3rem;">Timecard Sent Back</div>
                <div class="dm-comment-box"><strong>DM says:</strong> ${payload.dm_comment}</div>
                <p>Go to Timecards tab to modify your hours and resubmit.</p>
            </div>
        `;
    }

    if (payload.block_type === 'dm_timecard_review') {
        const flag = payload.has_extra ? ' <span class="extra-tag">HAS EXTRA HOURS</span>' : '';
        return `<div class="notif-content"><strong>${payload.employee_name}</strong> submitted their timecard for approval.${flag}<br><span class="muted">Go to Timecards tab to review.</span></div>`;
    }

    return `<div class="notif-content">${payload.message || JSON.stringify(payload)}</div>`;
}

function updateBadge(notifs) {
    const badge = document.getElementById('notif-badge');
    const count = Array.isArray(notifs) ? notifs.length : 0;
    badge.textContent = count;
    badge.style.display = count > 0 ? 'flex' : 'none';
}

// ─── ACTIONS ─────────────────────────────────────────────────────────────────

async function triggerMonday() {
    const res = await fetch('/api/monday/trigger', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
    loadDashboard();
}

async function triggerFriday() {
    const res = await fetch('/api/friday/trigger', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
    loadDashboard();
}

async function resetAll() {
    if (!confirm('Reset everything to initial state?')) return;
    await fetch('/api/reset', { method: 'POST' });
    showToast('All data reset.');
    loadDashboard();
}

// ─── MODAL ───────────────────────────────────────────────────────────────────

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('active');
    modalCallback = null;
}

function submitModal() {
    if (modalCallback) modalCallback();
}

// ─── UTILS ───────────────────────────────────────────────────────────────────

function showToast(msg) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
}

document.addEventListener('DOMContentLoaded', () => loadDashboard());

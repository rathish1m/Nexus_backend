(function () {
  // Utils
  function getCSRFToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      cookie = cookie.trim();
      if (cookie.startsWith(name + '=')) {
        return decodeURIComponent(cookie.substring(name.length + 1));
      }
    }
    return null;
  }

  function findContainer() {
    return document.getElementById('activationsContainer');
  }

  function getUrl(attr) {
    const c = findContainer();
    return c ? c.getAttribute(attr) : null;
  }

  // pagination state
  let currentPage = 1;
  let lastMeta = null;
  const defaultPageSize = 10;

  async function fetchPending(page = 1) {
    console.debug('fetchPending start');
    const tbody = document.getElementById('activationsBody');
    const msgEl = document.getElementById('activationMsg');
    const containerEl = findContainer();
    const loadingMsg = containerEl ? containerEl.getAttribute('data-loading-msg') : 'Loading...';
    const noPendingMsg = containerEl ? containerEl.getAttribute('data-no-pending-msg') : 'No pending activations.';
    const confirmLabel = containerEl ? containerEl.getAttribute('data-confirm-label') : 'Confirm';
    const cancelLabel = containerEl ? containerEl.getAttribute('data-cancel-label') : 'Cancel';
    msgEl.textContent = loadingMsg;
    tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-6 text-center text-gray-500">${loadingMsg}</td></tr>`;
    const refreshBtn = document.getElementById('refreshActivationsBtn');
    const spinner = document.getElementById('refreshSpinner');
    if (spinner) spinner.classList.remove('hidden');
    if (refreshBtn) refreshBtn.disabled = true;
    try {
      const pendingUrl = getUrl('data-pending-url') || '/tech/activation/api/pending/';
    const pageSizeAttr = containerEl.getAttribute('data-page-size') || '';
      const pageSize = pageSizeAttr ? Number(pageSizeAttr) : defaultPageSize;
      const url = new URL(pendingUrl, window.location.origin);
      url.searchParams.set('page', String(page));
      url.searchParams.set('page_size', String(pageSize));
      // apply filters from container attributes and filter inputs
      const statusAttr = containerEl ? containerEl.getAttribute('data-filter-status') : '';
      const dateRange = containerEl ? containerEl.getAttribute('data-filter-date_range') : '';
      const techSel = document.getElementById('kpiTechnician');
      const techId = techSel ? techSel.value : '';
      const statusSel = document.getElementById('filterStatus');
      const statusQ = statusSel ? statusSel.value : statusAttr || '';
      if (statusQ) url.searchParams.set('status', statusQ);
      if (dateRange) url.searchParams.set('date_range', dateRange);
      if (techId) url.searchParams.set('technician_id', techId);
      // search input removed; no search param
      console.debug('fetchPending -> requesting URL:', url.toString());
      const res = await fetch(url.toString(), { credentials: 'same-origin' });
      const data = await res.json();
      console.debug('fetchPending -> response data:', data);
      if (!data.success) throw new Error(data.error || 'Failed');

      const rows = data.pending_activations || [];
      console.debug('fetchPending -> rows.length:', rows.length, 'meta:', data.meta || null);
      // If meta present, use meta.total_items for message
      const meta = data.meta || null;
      msgEl.textContent = meta ? `${meta.total_items} pending activations` : `${rows.length} pending activations (fetched)`;
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="px-4 py-6 text-center text-gray-500">${noPendingMsg}</td></tr>`;
        renderPager(meta);
        return;
      }

      tbody.innerHTML = '';
      rows.forEach((r, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-gray-50';

        function coordinatesCell(obj) {
          // Normalize incoming plus_code (trim whitespace) and treat empty/whitespace as missing
          let plusRaw = obj.plus_code !== undefined && obj.plus_code !== null ? String(obj.plus_code) : '';
          let plus = plusRaw.trim();
          const lat = obj.latitude;
          const lng = obj.longitude;

          // If plus is empty string, try to compute using available Open Location Code globals.
          if (!plus && lat != null && lng != null) {
            try {
              const latNum = Number(lat);
              const lngNum = Number(lng);
              if (!Number.isFinite(latNum) || !Number.isFinite(lngNum)) {
                // invalid coordinates
                throw new Error('Invalid lat/lng');
              }

              // Support several possible global names/structures for the OLC lib
              const encCandidates = [
                typeof OpenLocationCode !== 'undefined' ? OpenLocationCode : null,
                typeof openlocationcode !== 'undefined' ? openlocationcode : null,
                typeof openLocationCode !== 'undefined' ? openLocationCode : null,
                (typeof window !== 'undefined' && window.OpenLocationCode) ? window.OpenLocationCode : null,
                (typeof window !== 'undefined' && window.openLocationCode) ? window.openLocationCode : null,
                (typeof window !== 'undefined' && window.openlocationcode) ? window.openlocationcode : null,
              ];

              let encoded = '';
              for (const cand of encCandidates) {
                if (!cand) continue;
                // direct encode
                if (typeof cand.encode === 'function') {
                  encoded = cand.encode(latNum, lngNum);
                }
                // nested object like { openlocationcode: { encode: fn } }
                else if (cand.openlocationcode && typeof cand.openlocationcode.encode === 'function') {
                  encoded = cand.openlocationcode.encode(latNum, lngNum);
                }
                // nested under OpenLocationCode property
                else if (cand.OpenLocationCode && typeof cand.OpenLocationCode.encode === 'function') {
                  encoded = cand.OpenLocationCode.encode(latNum, lngNum);
                }

                if (encoded) {
                  plus = String(encoded).trim();
                  console.debug('Computed plus_code from OLC', plus, 'using', cand);
                  break;
                }
              }
            } catch (e) {
              console.debug('OLC encode skipped/failed', e);
              plus = '';
            }
          }

          // If we now have a plus-code, display it as a small badge (clickable)
          if (plus) {
            const href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(plus)}`;
            return `<td class="px-4 py-3"><a target="_blank" rel="noopener" href="${href}" class="inline-flex items-center gap-2 px-2 py-1 rounded bg-gray-100 text-xs text-gray-800 hover:bg-gray-200">${plus}</a></td>`;
          }

          // Otherwise fall back to lat/lng link if available
          if (lat != null && lng != null) {
            const txt = `${lat}, ${lng}`;
            const href = `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
            return `<td class="px-4 py-3"><a target="_blank" rel="noopener" href="${href}" class="inline-flex items-center gap-2 px-2 py-1 rounded bg-gray-100 text-xs text-gray-800 hover:bg-gray-200">${txt}</a></td>`;
          }

          return `<td class="px-4 py-3 text-gray-500">—</td>`;
        }

        function statusBadge(st) {
          const s = (st || '').toLowerCase();
          let bg = 'bg-gray-200 text-gray-800';
          if (s === 'pending') bg = 'bg-amber-200 text-amber-800';
          else if (s === 'confirmed') bg = 'bg-emerald-200 text-emerald-800';
          else if (s === 'cancelled') bg = 'bg-red-200 text-red-800';
          return `<td class="px-4 py-3"><span class="inline-block px-2 py-1 text-xs rounded ${bg}">${st || '—'}</span></td>`;
        }

        const common = (idxDisplay, orderRef, userHtml, planName, kitHtml) => {
          return `
          <td class="px-4 py-3">${idxDisplay}</td>
          <td class="px-4 py-3 font-medium text-gray-900">${orderRef}</td>
          <td class="px-4 py-3">${userHtml}</td>
          <td class="px-4 py-3">${planName}</td>
          <td class="px-4 py-3">${kitHtml}</td>
        `;
      };

      const idxDisplay = idx + 1;
      const orderRef = r.order_ref || '—';
      const userHtml = `${r.user_name || '—'}<div class="text-xs text-gray-500">${r.user_email || ''}</div>`;
      const planName = r.plan_name || '—';
      const kitHtml = r.kit_id || '—';

      if (r.type === 'request') {
        // keep the full id including 'req-' prefix so server can distinguish ActivationRequest
        let idSegment = String(r.id || '');
        // Some APIs or transformations may return a bare numeric id for requests; ensure the 'req-' prefix is present
        if (!idSegment.startsWith('req-')) {
          // if it's numeric, prefix with req- to route to ActivationRequest; otherwise keep as-is
          if (/^\d+$/.test(idSegment)) idSegment = 'req-' + idSegment;
        }
        // Use server-rendered URL template to respect any i18n prefix or URL configuration.
        const containerEl = findContainer();
        const detailTemplate = containerEl ? containerEl.getAttribute('data-detail-url-template') : '/tech/activation/0/';
        // template is expected to end with '/0/' which we replace with /<id>/
        let detailsHref = detailTemplate;
        try {
          if (detailTemplate.indexOf('/0/') !== -1) {
            detailsHref = detailTemplate.replace('/0/', `/${idSegment}/`);
          } else if (detailTemplate.endsWith('/0')) {
            detailsHref = detailTemplate.replace(/0$/, idSegment);
          } else {
            // fallback: append id
            detailsHref = detailTemplate.replace(/\/$/, '') + '/' + idSegment + '/';
          }
        } catch (e) { detailsHref = `/tech/activation/${idSegment}/`; }
        tr.innerHTML = `
          ${common(idxDisplay, orderRef, userHtml, planName, kitHtml)}
          ${coordinatesCell(r)}
          ${statusBadge(r.status)}
          <td class="px-4 py-3 space-x-2">
            ${ (r.status && r.status.toLowerCase() === 'confirmed') ? `<button data-req-id="${r.id}" class="cancel-req px-3 py-1 rounded bg-red-600 text-white text-xs hover:bg-red-700">${cancelLabel}</button>` : `<button data-req-id="${r.id}" class="confirm-req px-3 py-1 rounded bg-emerald-600 text-white text-xs hover:bg-emerald-700">${confirmLabel}</button>` }
            ${(() => {
                const containerEl = findContainer();
                const label = containerEl ? containerEl.getAttribute('data-detail-label') : 'Details';
                return `<a href="${detailsHref}" target="_blank" rel="noopener" class="details-activation inline-block px-2 py-1 rounded bg-blue-600 text-white text-xs hover:bg-blue-700">${label}</a>`;
              })()}
          </td>
        `;
      } else {
        const idSegment = String(r.id || '');
        const containerEl = findContainer();
        const detailTemplate = containerEl ? containerEl.getAttribute('data-detail-url-template') : '/tech/activation/0/';
        let detailsHref = detailTemplate;
        try {
            if (detailTemplate.indexOf('/0/') !== -1) {
              detailsHref = detailTemplate.replace('/0/', `/${idSegment}/`);
            } else if (detailTemplate.endsWith('/0')) {
              detailsHref = detailTemplate.replace(/0$/, idSegment);
            } else {
              detailsHref = detailTemplate.replace(/\/$/, '') + '/' + idSegment + '/';
            }
          } catch (e) { detailsHref = `/tech/activation/${idSegment}/`; }
          tr.innerHTML = `
          ${common(idxDisplay, orderRef, userHtml, planName, kitHtml)}
          ${coordinatesCell(r)}
          ${statusBadge(r.status)}
          <td class="px-4 py-3 space-x-2">
            ${ (r.status && r.status.toLowerCase() === 'confirmed') ? `<button data-sub-id="${r.id}" class="cancel-sub px-3 py-1 rounded bg-red-600 text-white text-xs hover:bg-red-700">${cancelLabel}</button>` : `<button data-sub-id="${r.id}" class="confirm-sub px-3 py-1 rounded bg-emerald-600 text-white text-xs hover:bg-emerald-700">${confirmLabel}</button>` }
            ${(() => {
                const containerEl = findContainer();
                const label = containerEl ? containerEl.getAttribute('data-detail-label') : 'Details';
                return `<a href="${detailsHref}" target="_blank" rel="noopener" class="details-activation inline-block px-2 py-1 rounded bg-blue-600 text-white text-xs hover:bg-blue-700">${label}</a>`;
              })()}
          </td>
        `;
      }
      tbody.appendChild(tr);
    });
      // render pager
        renderPager(data.meta || null);
    } catch (err) {
      const statusText = (err && err.message) ? err.message : 'Fetch error';
      const tbodyEl = document.getElementById('activationsBody');
      tbodyEl.innerHTML = `<tr><td colspan="8" class="px-4 py-6 text-center text-red-600">${statusText}</td></tr>`;
      msgEl.textContent = `Error fetching activations: ${statusText}`;
      console.error('fetchPending error:', err);
    } finally {
      if (spinner) spinner.classList.add('hidden');
      if (refreshBtn) refreshBtn.disabled = false;
    }
  }

    function renderPager(meta) {
      const pager = document.getElementById('activationsPager');
      if (!pager) return;
      pager.innerHTML = '';
      if (!meta) return;
    const page = meta.page || 1;
    const total = meta.total_pages || 1;
    currentPage = page;
    lastMeta = meta;

    const isCompact = window.matchMedia && window.matchMedia('(max-width: 640px)').matches;

      const prevLabel = getUrl('data-prev-label') || 'Prev';
      const nextLabel = getUrl('data-next-label') || 'Next';

      const prev = document.createElement('button');
      prev.className = 'px-2 py-1 rounded border bg-white';
      prev.disabled = page <= 1;
      prev.setAttribute('aria-label', `${prevLabel}`);
      prev.textContent = '‹ ' + prevLabel;
      prev.addEventListener('click', () => { fetchPending(Math.max(1, page - 1)); });

      const next = document.createElement('button');
      next.className = 'px-2 py-1 rounded border bg-white';
      next.disabled = page >= total;
      next.setAttribute('aria-label', `${nextLabel}`);
      next.textContent = nextLabel + ' ›';
      next.addEventListener('click', () => { fetchPending(Math.min(total, page + 1)); });

      // numeric pages: show a window around current page, display ellipses when needed
      const pagesWindow = 3; // pages before/after current
      const start = Math.max(1, page - pagesWindow);
      const end = Math.min(total, page + pagesWindow);

      if (isCompact) {
        // compact mode: only Prev / Next and a small current-page badge
        pager.appendChild(prev);
        const pageBadge = document.createElement('span');
        pageBadge.className = 'px-2 py-1 text-sm text-gray-700';
        pageBadge.textContent = `${page}`; // show only current page number (no total)
        pager.appendChild(pageBadge);
        pager.appendChild(next);
      } else {
        pager.appendChild(prev);

        // first page shortcut and leading ellipsis
        if (start > 1) {
          const firstBtn = document.createElement('button');
          firstBtn.className = 'px-2 py-1 rounded border bg-white';
          firstBtn.textContent = '1';
          firstBtn.addEventListener('click', () => { fetchPending(1); });
          pager.appendChild(firstBtn);
          if (start > 2) {
            const gap = document.createElement('span');
            gap.className = 'px-2 text-gray-500';
            gap.textContent = '...';
            pager.appendChild(gap);
          }
        }

        for (let p = start; p <= end; p++) {
          const btn = document.createElement('button');
          btn.className = 'px-2 py-1 rounded border bg-white';
          if (p === page) {
            btn.className += ' bg-gray-100 font-semibold';
            btn.setAttribute('aria-current', 'page');
          }
          btn.textContent = String(p);
          btn.addEventListener('click', () => { fetchPending(p); });
          pager.appendChild(btn);
        }

        // trailing ellipsis and last page shortcut
        if (end < total) {
          if (end < total - 1) {
            const gap2 = document.createElement('span');
            gap2.className = 'px-2 text-gray-500';
            gap2.textContent = '...';
            pager.appendChild(gap2);
          }
          const lastBtn = document.createElement('button');
          lastBtn.className = 'px-2 py-1 rounded border bg-white';
          lastBtn.textContent = String(total);
          lastBtn.addEventListener('click', () => { fetchPending(total); });
          pager.appendChild(lastBtn);
        }

        pager.appendChild(next);
      }
    }

    async function postToUrl(url, opts) {
      return fetch(url, Object.assign({ method: 'POST', headers: { 'X-CSRFToken': getCSRFToken() } }, opts || {})).then(r => r.json());
    }

    function attachActions() {
      document.addEventListener('click', async (ev) => {
        const t = ev.target;
        if (t.matches('.confirm-req')) {
          const id = t.getAttribute('data-req-id').replace('req-','');
          const template = getUrl('data-confirm-activation-request-url-template');
          const url = template.replace('/0/', `/${id}/`);
          t.disabled = true;
          const res = await postToUrl(url);
          document.getElementById('activationMsg').innerText = res.message || res.error || '';
          if (res.success) fetchPending();
          t.disabled = false;
        } else if (t.matches('.cancel-req')) {
          const id = t.getAttribute('data-req-id').replace('req-','');
          const template = getUrl('data-cancel-activation-request-url-template');
          const url = template.replace('/0/', `/${id}/`);
          t.disabled = true;
          const res = await postToUrl(url);
          document.getElementById('activationMsg').innerText = res.message || res.error || '';
          if (res.success) fetchPending();
          t.disabled = false;
        } else if (t.matches('.confirm-sub')) {
          const id = t.getAttribute('data-sub-id');
          const template = getUrl('data-confirm-activation-url-template');
          const url = template.replace('/0/', `/${id}/`);
          t.disabled = true;
          const res = await postToUrl(url);
          document.getElementById('activationMsg').innerText = res.message || res.error || '';
          if (res.success) fetchPending();
          t.disabled = false;
        } else if (t.matches('.cancel-sub')) {
          const id = t.getAttribute('data-sub-id');
          const template = getUrl('data-cancel-activation-url-template');
          const url = template.replace('/0/', `/${id}/`);
          t.disabled = true;
          const res = await postToUrl(url);
          document.getElementById('activationMsg').innerText = res.message || res.error || '';
          if (res.success) fetchPending();
          t.disabled = false;
        }
      // note: details links are now standard anchors to server-rendered pages; do not intercept click
    });
  }

  async function openActivationDetails(activationId) {
    // Ensure modal container exists
    let modal = document.getElementById('activationDetailsModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'activationDetailsModal';
      modal.className = 'fixed inset-0 z-50 hidden';
      modal.innerHTML = `
        <div class="fixed inset-0 bg-black bg-opacity-40" data-close="overlay"></div>
        <div class="absolute right-0 top-0 max-w-md w-full h-full bg-white shadow-lg overflow-auto p-6">
          <div id="activationDetailsContent">Loading...</div>
          <div class="mt-4 text-right"><button id="activationDetailsClose" class="px-3 py-1 rounded bg-gray-200">Close</button></div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector('[data-close="overlay"]').addEventListener('click', () => { modal.classList.add('hidden'); });
      document.addEventListener('click', (ev) => { if (ev.target && ev.target.id === 'activationDetailsClose') modal.classList.add('hidden'); });
    }

    modal.classList.remove('hidden');
    const content = document.getElementById('activationDetailsContent');
    content.innerHTML = 'Loading details...';

    const urlTemplate = getUrl('data-activation-detail-url-template') || '/tech/activation/details/';
    // normalize activation id (some ids already have req- prefix)
    const aid = activationId;
    const url = urlTemplate.endsWith('/') ? `${urlTemplate}${aid}/` : `${urlTemplate}/${aid}/`;
    try {
      const res = await fetch(url, { credentials: 'same-origin' });
      const data = await res.json();
      if (!data.success) {
        content.innerHTML = `<div class="text-red-600">${data.error || 'Failed to load details'}</div>`;
        return;
      }
      const a = data.activation;
      const html = `
        <h3 class="text-lg font-semibold mb-2">${a.order_ref || a.plan_name || 'Activation details'}</h3>
        <div class="text-sm text-gray-700"><strong>Type:</strong> ${a.type}</div>
        <div class="mt-3 text-sm"><strong>Order ref:</strong> ${a.order_ref || '—'}</div>
        <div class="text-sm"><strong>Plan:</strong> ${a.plan_name || '—'}</div>
        <div class="text-sm"><strong>Kit serial:</strong> ${a.kit_serial || '—'}</div>
        <div class="text-sm"><strong>Requested by:</strong> ${a.requested_by || '—'}</div>
        <div class="text-sm"><strong>Requested at:</strong> ${a.requested_at || '—'}</div>
        <div class="mt-3 text-sm"><strong>Client:</strong> ${a.client_name || (a.user_name || '—')}</div>
        <div class="mt-2 text-sm"><strong>Contact:</strong> ${a.user_email || ''}</div>
        <div class="mt-2 text-sm"><strong>Plus code:</strong> ${a.plus_code || '—'}</div>
      `;
      content.innerHTML = html;
    } catch (err) {
      content.innerHTML = `<div class="text-red-600">Error loading details</div>`;
      console.error(err);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const refreshBtn = document.getElementById('refreshActivationsBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', () => fetchPending(1));
    attachActions();
    // Ensure Open Location Code library is available before first fetch if possible.
    // If it's not present, dynamically load it from CDN and then fetch; if loading fails, continue without it.
    const OLC_CDN = 'https://cdn.jsdelivr.net/npm/open-location-code@1.0.4/openlocationcode.min.js';
    function hasOLC() {
      return (
        (typeof OpenLocationCode !== 'undefined' && OpenLocationCode && typeof OpenLocationCode.encode === 'function') ||
        (typeof openlocationcode !== 'undefined' && openlocationcode && typeof openlocationcode.encode === 'function') ||
        (typeof openLocationCode !== 'undefined' && openLocationCode && typeof openLocationCode.encode === 'function') ||
        (typeof window !== 'undefined' && window.OpenLocationCode && typeof window.OpenLocationCode.encode === 'function')
      );
    }

    async function ensureOLCAndFetch() {
      if (hasOLC()) return fetchPending();
      // Try to load the CDN script dynamically
      try {
        await new Promise((resolve, reject) => {
          const s = document.createElement('script');
          s.src = OLC_CDN;
          s.async = true;
          s.onload = () => resolve();
          s.onerror = (e) => reject(new Error('Failed to load OLC script'));
          document.head.appendChild(s);
          // safety timeout
          setTimeout(() => resolve(), 2500);
        });
      } catch (e) {
        console.debug('Could not dynamically load OLC lib:', e);
      } finally {
        // proceed either way
        fetchPending();
      }
    }

    // initial fetch (deferred until OLC load attempt)
    ensureOLCAndFetch();

    // KPI: fetch and populate cards, and populate technician selector
    async function fetchKpis() {
      try {
        const containerEl = findContainer();
        const pendingUrl = getUrl('data-pending-url') || '/tech/activation/api/pending/';
        const base = containerEl ? containerEl.getAttribute('data-pending-url') : '/tech/activation/';
        const kpiUrl = (containerEl && containerEl.getAttribute('data-kpi-url')) || '/tech/activation/api/kpis/';
        const techSelect = document.getElementById('kpiTechnician');

        // populate technicians select (if empty)
        if (techSelect && techSelect.options.length <= 1) {
            try {
              const res = await fetch('/tech/get_technician/');
              const json = await res.json();
              let list = [];
              // Support two shapes: plain array, or object { technicians: [...] }
              if (Array.isArray(json)) list = json;
              else if (json && Array.isArray(json.technicians)) list = json.technicians;
              else if (json && Array.isArray(json.data)) list = json.data; // fallback

              if (list.length) {
                list.forEach(t => {
                  const opt = document.createElement('option');
                  opt.value = t.id || t.id_user || t.id || '';
                  opt.textContent = t.full_name || t.name || t.username || String(opt.value);
                  techSelect.appendChild(opt);
                });
              } else {
                console.debug('No technicians returned from /tech/get_technician/:', json);
              }
            } catch (e) { console.debug('Failed to load technicians', e); }
        }

        // fetch KPIs with current filter values
  const techId = techSelect ? techSelect.value : '';
  const rangeBtn = document.querySelector('.kpi-range.active');
  const range = rangeBtn ? rangeBtn.getAttribute('data-range') : '';
  const statusSel = document.getElementById('filterStatus');
  const statusQ = statusSel ? statusSel.value : (containerEl ? containerEl.getAttribute('data-filter-status') : '');
  const url = new URL(kpiUrl, window.location.origin);
  if (techId) url.searchParams.set('technician_id', techId);
  if (range) url.searchParams.set('date_range', range);
  if (statusQ) url.searchParams.set('status', statusQ);
  const kres = await fetch(url.toString(), { credentials: 'same-origin' });
  const kdata = await kres.json();
        if (!kdata.success) return;
        const k = kdata.kpis || {};
        document.getElementById('kpi_planned_today').textContent = k.planned_today || 0;
        document.getElementById('kpi_pending').textContent = k.pending || 0;
        document.getElementById('kpi_in_progress').textContent = k.in_progress || 0;
        document.getElementById('kpi_completed').textContent = k.completed || 0;
      } catch (err) {
        console.debug('fetchKpis error', err);
      }
    }

    // wire KPI card clicks and filter controls
    document.addEventListener('click', (ev) => {
      const t = ev.target;
      const card = t.closest && t.closest('[data-kpi]');
      if (card) {
        const k = card.getAttribute('data-kpi');
        const containerEl = findContainer();
        // apply filter: for 'pending' set status=pending, etc.
        if (k === 'pending') {
          containerEl && containerEl.setAttribute('data-filter-status', 'pending');
        } else if (k === 'in_progress') {
          containerEl && containerEl.setAttribute('data-filter-status', 'in_progress');
        } else if (k === 'completed') {
          containerEl && containerEl.setAttribute('data-filter-status', 'active');
        } else if (k === 'planned_today') {
          containerEl && containerEl.setAttribute('data-filter-date_range', '24h');
        }
        // refresh table to page 1
        fetchPending(1);
      }
      // date range buttons
      if (t.matches && t.matches('.kpi-range')) {
        document.querySelectorAll('.kpi-range').forEach(b => b.classList.remove('active'));
        t.classList.add('active');
        fetchKpis();
      }
    });

    // technician select change
    const techSelect = document.getElementById('kpiTechnician');
    if (techSelect) techSelect.addEventListener('change', () => { fetchKpis(); fetchPending(1); });

  // status select change
  const statusSelect = document.getElementById('filterStatus');
  if (statusSelect) statusSelect.addEventListener('change', () => { fetchKpis(); fetchPending(1); });

    // initial KPIs
    fetchKpis();

    // re-render pager on resize using cached meta
    let resizeTimer = null;
    window.addEventListener('resize', () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { if (lastMeta) renderPager(lastMeta); }, 120);
    });
  });

  // expose for debug if needed
  window._nexus_fetchPending = fetchPending;
})();

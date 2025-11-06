/* ==================== CONFIG ==================== */
const API_BASE = 'http://localhost:8000';
let currentCompany = '', currentJob = '';

/* ==================== AUTH BOOTSTRAP ==================== */
const AUTH_TOKEN_KEY = 'auth_token';
let userRole = 'user';
let allCompanies = [];

function getAuthToken() { return localStorage.getItem(AUTH_TOKEN_KEY); }
function requireAuth() { 
  const token = getAuthToken();
  if(!token) { 
    window.location.href = '/static/login.html';
    return false;
  }
  return true;
}
if (!requireAuth()) {
  // No token, will redirect
} else {
  // Token exists, will be verified by server
}

// Unified auth-aware fetch wrapper
async function authFetch(url, options = {}) {
  const token = getAuthToken();
  options.headers = options.headers || {};
  if (token) {
    if (!options.headers['Authorization']) options.headers['Authorization'] = `Bearer ${token}`;
  }
  const resp = await fetch(url, options);
  if (resp.status === 401) {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    window.location.href = '/static/login.html';
    return resp;
  }
  return resp;
}

// Verify admin access
(async function initAdminCheck(){
  try {
    console.log('[Admin Auth] Checking authentication...');
    const r = await authFetch(`${API_BASE}/auth/me`);
    if(r.ok) {
      const me = await r.json();
      console.log('[Admin Auth] Authentication successful:', me.email, 'Role:', me.role);
      userRole = me.role;
      
      // Redirect non-admins to user page
      if (userRole !== 'admin') {
        console.log('[Admin Auth] Non-admin user, redirecting to user page');
        window.location.href = '/static/index.html';
        return;
      }
      
      const el = document.getElementById('admin-info');
      if (el) { 
        el.innerHTML = `
          <span class="text-gray-700">${me.email}</span>
          <span class="bg-red-600 text-white text-xs font-bold px-2 py-1 rounded ml-2">ADMIN</span>
        `;
        el.classList.remove('hidden'); 
      }
      
      // Show page BEFORE setup functions to ensure it's always visible
      console.log('[Admin Auth] Revealing page...');
      document.body.classList.remove('auth-checking');
      
      // Highlight dashboard tab on initial load
      $$('.tab-link').forEach(l => {
        if (l.dataset.tab === 'dashboard') {
          l.classList.add('text-blue-700', 'font-medium');
          l.classList.remove('text-gray-600');
        }
      });
      
      // Load initial data
      loadAllCompanies();
      loadUserStats();
    } else {
      // Auth failed, redirect will happen in authFetch
      console.log('[Admin Auth] Authentication failed, redirecting to login');
      window.location.href = '/static/login.html';
    }
  } catch(e){ 
    console.error('[Admin Auth] Error during authentication:', e);
    window.location.href = '/static/login.html';
  }
})();

// Logout handler
document.getElementById('logout-btn')?.addEventListener('click', () => {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  window.location.href = '/static/login.html';
});

/* ==================== HELPERS ==================== */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function showToast(msg, error = false) {
  const toast = $('#toast');
  const msgEl = $('#toast-message');
  toast.className = error
    ? 'fixed bottom-4 right-4 bg-red-600 text-white px-6 py-3 rounded-lg shadow-lg flex items-center space-x-3'
    : 'fixed bottom-4 right-4 bg-green-600 text-white px-6 py-3 rounded-lg shadow-lg flex items-center space-x-3';
  msgEl.textContent = msg;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 4000);
}

function addActivity(msg) {
  const log = $('#activity-log');
  if (!log) return;
  const p = document.createElement('p');
  p.textContent = `${new Date().toLocaleTimeString()} — ${msg}`;
  log.insertBefore(p, log.firstChild);
}

/* ==================== LOAD ALL COMPANIES ==================== */
async function loadAllCompanies() {
  try {
    const res = await authFetch(`${API_BASE}/companies/`);
    const data = await res.json();
    allCompanies = data.companies || [];
    
    // Populate company datalists
    const cvList = document.getElementById('company-list');
    const jdList = document.getElementById('jd-company-list');
    const searchSelect = document.getElementById('search-company');
    
    if (cvList) {
      cvList.innerHTML = '';
      allCompanies.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c;
        cvList.appendChild(opt);
      });
    }
    
    if (jdList) {
      jdList.innerHTML = '';
      allCompanies.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c;
        jdList.appendChild(opt);
      });
    }
    
    if (searchSelect) {
      searchSelect.innerHTML = '<option value="">Select Company</option>';
      allCompanies.forEach(c => searchSelect.appendChild(new Option(c, c)));
    }
    
    // Update KPI
    document.getElementById('kpi-companies').textContent = allCompanies.length;
  } catch (err) {
    console.error('Failed to load companies', err);
  }
}

async function loadUserStats() {
  try {
    const res = await authFetch(`${API_BASE}/auth/admin/users`);
    const data = await res.json();
    document.getElementById('kpi-users').textContent = data.users?.length || 0;
  } catch (err) {
    console.error('Failed to load user stats', err);
  }
}

/* ==================== TAB NAVIGATION ==================== */
$$('.tab-link').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const tab = link.dataset.tab;
    
    // Hide all sections
    $$('section').forEach(s => s.classList.add('hidden'));
    $(`#${tab}`).classList.remove('hidden');

    // Update active tab styling
    $$('.tab-link').forEach(l => {
      l.classList.remove('text-blue-700', 'font-medium');
      l.classList.add('text-gray-600');
    });
    
    // Highlight clicked tab (all instances with same data-tab)
    $$(`[data-tab="${tab}"]`).forEach(l => {
      l.classList.remove('text-gray-600');
      l.classList.add('text-blue-700', 'font-medium');
    });

    if (tab === 'dashboard') loadDashboard();
    if (tab === 'users') refreshUsers();
    if (tab === 'data-browser') loadDataBrowser();
    if (tab === 'bulk-ops') loadBulkOpsDropdowns();
    if (tab === 'maintenance') loadMaintenanceDropdowns();
    if (tab === 'logs') loadLogs();
  });
});

/* ==================== DRAG & DROP ==================== */
function setupDropzone(zoneId) {
  const zone = $(`#${zoneId}`);
  if (!zone) return;
  const input = zone.querySelector('input[type="file"]');
  
  // For CV dropzone (multiple files)
  if (zoneId === 'cv-dropzone') {
    const info = $('#cv-file-info');
    const fileList = $('#cv-file-list');
    const fileCount = $('#cv-file-count');
    
    zone.addEventListener('click', () => input.click());
    
    input.addEventListener('change', () => {
      if (input.files.length > 0) {
        updateCVFileList(input.files);
        info.classList.remove('hidden');
      }
    });
    
    ['dragover', 'dragleave', 'drop'].forEach(ev => {
      zone.addEventListener(ev, e => {
        e.preventDefault();
        zone.classList.toggle('drag-over', ev.type === 'dragover');
        if (ev.type === 'drop' && e.dataTransfer.files.length > 0) {
          input.files = e.dataTransfer.files;
          input.dispatchEvent(new Event('change'));
        }
      });
    });
    
    function updateCVFileList(files) {
      fileList.innerHTML = '';
      fileCount.textContent = files.length;
      Array.from(files).forEach((file, index) => {
        const div = document.createElement('div');
        div.className = 'flex justify-between items-center text-sm py-1 px-2 bg-white rounded';
        div.innerHTML = `
          <span class="text-gray-700">${file.name}</span>
          <span class="text-gray-500 text-xs">${(file.size / 1024).toFixed(1)} KB</span>
        `;
        fileList.appendChild(div);
      });
    }
  } else {
    // For JD dropzone (single file)
    const info = $(`#${zoneId.replace('-dropzone', '-file-info')}`);
    const nameSpan = $(`#${zoneId.replace('-dropzone', '-file-name')}`);
    
    zone.addEventListener('click', () => input.click());
    
    input.addEventListener('change', () => {
      if (input.files[0]) {
        nameSpan.textContent = input.files[0].name;
        info.classList.remove('hidden');
      }
    });
    
    ['dragover', 'dragleave', 'drop'].forEach(ev => {
      zone.addEventListener(ev, e => {
        e.preventDefault();
        zone.classList.toggle('drag-over', ev.type === 'dragover');
        if (ev.type === 'drop' && e.dataTransfer.files[0]) {
          input.files = e.dataTransfer.files;
          input.dispatchEvent(new Event('change'));
        }
      });
    });
  }
}
setupDropzone('cv-dropzone');
setupDropzone('jd-dropzone');

/* Clear CV files button */
$('#cv-clear-files')?.addEventListener('click', () => {
  const input = $('#cv-dropzone input');
  input.value = '';
  $('#cv-file-info').classList.add('hidden');
  $('#cv-file-list').innerHTML = '';
  $('#cv-file-count').textContent = '0';
});

/* Clear JD file button */
$('#jd-clear-file')?.addEventListener('click', () => {
  const input = $('#jd-dropzone input');
  input.value = '';
  $('#jd-file-info').classList.add('hidden');
  $('#jd-file-name').textContent = '';
});

/* ==================== UPLOAD CV ==================== */
$('#cv-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const submitBtn = form.querySelector('button[type="submit"]');
  const spinner = $('#cv-spinner');
  const text = $('#cv-submit-text');
  const progressDiv = $('#cv-upload-progress');
  const progressBar = $('#cv-progress-bar');
  const progressText = $('#cv-progress-text');

  const input = form.querySelector('input[type="file"]');
  const files = Array.from(input.files);
  
  if (files.length === 0) {
    showToast('Please select at least one CV file', true);
    return;
  }

  const company = form.querySelector('input[name="company_name"]').value;
  const job = form.querySelector('input[name="job_title"]').value;

  submitBtn.disabled = true;
  spinner.classList.remove('hidden');
  text.textContent = 'Processing...';
  progressDiv.classList.remove('hidden');

  let successCount = 0;
  let duplicateCount = 0;
  let errorCount = 0;

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const formData = new FormData();
    formData.append('company_name', company);
    formData.append('job_title', job);
    formData.append('file', file);

    // Update progress
    const percent = ((i + 1) / files.length) * 100;
    progressBar.style.width = `${percent}%`;
    progressText.textContent = `Uploading ${i + 1} of ${files.length}: ${file.name}`;

    console.log(`[CV Upload] Starting upload ${i + 1}/${files.length}: ${file.name} (${file.size} bytes)`);

    try {
      const res = await authFetch(`${API_BASE}/upload-cv/`, { method: 'POST', body: formData });
      console.log(`[CV Upload] Response status: ${res.status}`);
      
      const data = await res.json();
      console.log(`[CV Upload] Response data:`, data);
      
      if (!res.ok) {
        errorCount++;
        console.error(`[CV Upload] Failed to upload ${file.name}:`, data.detail || data);
      } else if (data.duplicate_within_job || data.existing_other_job_same_company) {
        duplicateCount++;
        console.log(`[CV Upload] ${file.name} is a duplicate`);
      } else {
        successCount++;
        console.log(`[CV Upload] ${file.name} uploaded successfully`);
      }
    } catch (err) {
      errorCount++;
      console.error(`[CV Upload] Error uploading ${file.name}:`, err);
    }
  }

  currentCompany = company;
  currentJob = job;

  // Show summary
  let message = `Upload complete: ${successCount} successful`;
  if (duplicateCount > 0) message += `, ${duplicateCount} duplicates`;
  if (errorCount > 0) message += `, ${errorCount} errors`;
  
  showToast(message, errorCount > 0);
  addActivity(`Uploaded ${successCount} CVs for ${job} at ${company}`);
  
  loadAllCompanies();
  form.reset();
  $('#cv-file-info').classList.add('hidden');
  $('#cv-file-list').innerHTML = '';
  $('#cv-file-count').textContent = '0';
  progressDiv.classList.add('hidden');
  progressBar.style.width = '0%';
  
  submitBtn.disabled = false;
  spinner.classList.add('hidden');
  text.textContent = 'Parse & Save CVs';
});

/* ==================== UPLOAD JD ==================== */
$('#jd-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const submitBtn = form.querySelector('button[type="submit"]');
  const spinner = $('#jd-spinner');
  const text = $('#jd-submit-text');

  submitBtn.disabled = true;
  spinner.classList.remove('hidden');
  text.textContent = 'Saving...';

  const formData = new FormData(form);
  try {
    const res = await authFetch(`${API_BASE}/upload-jd/`, { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'JD upload failed');

    currentCompany = formData.get('company_name');
    currentJob = formData.get('job_title');

    if (data.existing) {
      showToast('JD already exists');
    } else {
      showToast('JD saved and embedded!');
      addActivity(`Uploaded JD: ${currentJob} at ${currentCompany}`);
    }
    
    loadAllCompanies();
    form.reset();
  } catch (err) {
    showToast(err.message, true);
  } finally {
    submitBtn.disabled = false;
    spinner.classList.add('hidden');
    text.textContent = 'Save JD';
  }
});

/* ==================== SEARCH & RANK ==================== */
console.log('[Init] Setting up search functionality...');
const searchCompanySelect = $('#search-company');
const searchBtn = $('#search-btn');

console.log('[Init] Search company select:', searchCompanySelect);
console.log('[Init] Search button:', searchBtn);

if (!searchBtn) {
  console.error('[Init] CRITICAL: Search button (#search-btn) not found in DOM!');
} else {
  console.log('[Init] Search button found:', searchBtn.id, searchBtn.className);
}

if (searchCompanySelect) {
  searchCompanySelect.addEventListener('change', async e => {
    const company = e.target.value;
    const jobSelect = $('#search-job');
    jobSelect.innerHTML = '<option>Loading...</option>';
    jobSelect.disabled = true;
    if (!company) return;

    try {
      const res = await authFetch(`${API_BASE}/jobs/?company_name=${encodeURIComponent(company)}`);
      const { jobs } = await res.json();
      jobSelect.innerHTML = '<option value="">Select Job</option>';
      jobs.forEach(j => jobSelect.appendChild(new Option(j, j)));
      jobSelect.disabled = false;
    } catch (err) {
      showToast('Failed to load jobs', true);
    }
  });
}

if (searchBtn) {
  console.log('[Init] Adding click listener to search button');
  console.log('[Init] Button disabled state:', searchBtn.disabled);
  console.log('[Init] Button parent:', searchBtn.parentElement);
  
  searchBtn.addEventListener('click', async (event) => {
    console.log('[Search] addEventListener fired!', event);
    console.log('[Search] Button clicked!');
    const company = $('#search-company').value;
    const job = $('#search-job').value;
    
    if (!company || !job) {
      return showToast('Please select both company and job title', true);
    }

    const btn = $('#search-btn');
    const spinner = $('#search-spinner');
    const btnText = btn.querySelector('span');
    const originalText = btnText.textContent;
    
    btn.disabled = true;
    spinner.classList.remove('hidden');
    btnText.textContent = 'Searching...';

    console.log(`[Search] Starting search for company: ${company}, job: ${job}`);

    try {
      const res = await authFetch(`${API_BASE}/search-cvs/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_name: company, job_title: job, top_k_cvs: 10, show_details: true })
      });
      
      console.log(`[Search] Response status: ${res.status}`);
      const data = await res.json();
      console.log(`[Search] Response data:`, data);
      
      // Log vector search and reranking status
      console.log(`[Search] Cross-encoder enabled: ${data.cross_encoder_enabled}`);
      console.log(`[Search] Rerank mode: ${data.rerank_mode}`);
      console.log(`[Search] JD ID used: ${data.jd_id_used}`);
      console.log(`[Search] Blend alpha: ${data.blend_alpha}`);
      console.log(`[Search] Number of results: ${data.results?.length || 0}`);
      
      // Log ALL result scores for comparison
      if (data.results && data.results.length > 0) {
        console.log('[Search] All result scores:');
        data.results.forEach((r, idx) => {
          console.log(`  ${idx + 1}. ${r.original_identifier || r.cv_id}`);
          console.log(`     Vector: ${r.total_score?.toFixed(4)}, Reranker: ${r.cross_encoder_score?.toFixed(4)}, Combined: ${r.combined_score?.toFixed(4)}`);
        });
      }
      
      if (!res.ok) {
        const errorMsg = data.detail || 'Search failed';
        console.error(`[Search] Error:`, errorMsg);
        
        // Provide helpful error messages
        if (errorMsg.includes('Job description not found') || errorMsg.includes('JD not found')) {
          showToast(`No job description found for ${job}. Please upload a JD first.`, true);
        } else if (errorMsg.includes('No CVs') || errorMsg.includes('no CVs')) {
          showToast(`No CVs found for ${job}. Please upload CVs first.`, true);
        } else {
          showToast(errorMsg, true);
        }
        return;
      }

      if (!data.results || data.results.length === 0) {
        showToast('No matching CVs found. Try uploading more CVs.', true);
        return;
      }

      currentCompany = company;
      currentJob = job;
      displayResults(data.results);
      addActivity(`Searched CVs for ${job} at ${company} - Found ${data.results.length} matches`);
      showToast(`Found ${data.results.length} matching CVs`);
      
    } catch (err) {
      console.error(`[Search] Exception:`, err);
      showToast(`Search error: ${err.message}`, true);
    } finally {
      btn.disabled = false;
      spinner.classList.add('hidden');
      btnText.textContent = originalText;
    }
  });
}
else {
  console.error('[Init] Search button not found!');
}

function displayResults(results) {
  const container = $('#results-list');
  const count = $('#result-count');
  count.textContent = results.length;
  container.innerHTML = '';
  $('#search-results').classList.remove('hidden');

  results.forEach((r, index) => {
    const score = (r.combined_score ?? r.total_score ?? 0).toFixed(3);
    const vectorScore = (r.total_score ?? 0).toFixed(3);
    const ceScore = r.cross_encoder_score !== null && r.cross_encoder_score !== undefined 
      ? r.cross_encoder_score.toFixed(3) 
      : null;
    
    // Determine if reranking was applied
    const hasReranking = ceScore !== null;
    const scoreLabel = hasReranking ? 'Combined Score' : 'Vector Score';
    const scoreColor = hasReranking ? 'text-purple-700' : 'text-blue-700';
    
    const card = document.createElement('div');
    card.className = 'bg-white p-5 rounded-lg shadow-sm border mb-4';
    card.innerHTML = `
      <div class="flex justify-between items-start mb-4">
        <div class="flex-1">
          <h4 class="font-semibold text-lg">${r.original_identifier || r.cv_id}</h4>
          <p class="text-sm text-gray-600">CV ID: ${r.cv_id}</p>
          ${hasReranking ? '<span class="inline-block mt-1 text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded"><i class="fas fa-layer-group"></i> Reranked</span>' : ''}
        </div>
        <div class="text-right flex-shrink-0">
          <p class="text-2xl font-bold ${scoreColor}">${score}</p>
          <p class="text-xs text-gray-500">${scoreLabel}</p>
          ${hasReranking ? `
            <div class="mt-2 text-xs text-gray-600">
              <div>Vector: ${vectorScore}</div>
              <div>Reranker: ${ceScore}</div>
            </div>
          ` : ''}
          <button class="view-cv-btn mt-2 bg-blue-600 hover:bg-blue-700 text-white text-xs px-3 py-1 rounded" data-cv-id="${r.cv_id}">
            <i class="fas fa-eye"></i> View CV
          </button>
        </div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-gray-600">
        ${Object.entries(r.section_scores || {}).map(([k,v]) => 
          `<div><span class="font-medium">${k}:</span> ${v.toFixed(2)}</div>`
        ).join('')}
      </div>
    `;
    container.appendChild(card);
  });
}

/* ==================== DASHBOARD ==================== */
async function loadDashboard() {
  if (!currentCompany || !currentJob) {
    $('#top-candidates').innerHTML = '<p class="text-sm text-gray-500 italic">Select a company and job to see rankings</p>';
    $('#kpi-cvs').textContent = '0';
    $('#kpi-jobs').textContent = allCompanies.length;
    return;
  }

  try {
    // Get CV count for this job
    const cvRes = await authFetch(`${API_BASE}/existing-cvs/?company_name=${encodeURIComponent(currentCompany)}&job_title=${encodeURIComponent(currentJob)}`);
    
    if (!cvRes.ok) {
      $('#top-candidates').innerHTML = '<p class="text-sm text-gray-500 italic">No data found for this job</p>';
      $('#kpi-cvs').textContent = '0';
      return;
    }

    const cvData = await cvRes.json();
    const cvs = cvData.cvs || [];
    $('#kpi-cvs').textContent = cvs.length;

    if (cvs.length === 0) {
      $('#top-candidates').innerHTML = '<p class="text-sm text-gray-500 italic">No CVs uploaded for this job yet</p>';
      return;
    }

    // Run search to get ranked results
    const searchRes = await authFetch(`${API_BASE}/search-cvs/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_name: currentCompany, job_title: currentJob, top_k_cvs: 5, show_details: true })
    });
    
    if (!searchRes.ok) {
      $('#top-candidates').innerHTML = '<p class="text-sm text-gray-500 italic">Error loading rankings</p>';
      return;
    }

    const data = await searchRes.json();
    const results = data.results || [];
    
    const container = $('#top-candidates');
    container.innerHTML = '';
    
    if (results.length > 0) {
      results.forEach((r, i) => {
        const score = (r.combined_score ?? r.total_score ?? 0).toFixed(2);
        const div = document.createElement('div');
        div.className = 'flex justify-between items-center py-2 border-b';
        div.innerHTML = `
          <div class="flex items-center space-x-3">
            <span class="font-bold text-blue-700">#${i+1}</span>
            <span class="text-sm">${r.original_identifier || r.cv_id}</span>
          </div>
          <span class="font-semibold text-green-700">${score}%</span>
        `;
        container.appendChild(div);
      });
    } else {
      container.innerHTML = '<p class="text-sm text-gray-500 italic">No rankings available</p>';
    }
  } catch (err) {
    console.error('Dashboard load failed', err);
    $('#top-candidates').innerHTML = '<p class="text-sm text-gray-500 italic">Error loading dashboard</p>';
  }
}

/* ==================== USER MANAGEMENT ==================== */
async function refreshUsers() {
  try {
    const res = await authFetch(`${API_BASE}/auth/admin/users`);
    const data = await res.json();
    const list = $('#users-list');
    list.innerHTML = '';
    
    if (data.users && data.users.length > 0) {
      data.users.forEach(u => {
        const div = document.createElement('div');
        div.className = 'bg-gray-50 p-3 rounded border text-sm';
        div.innerHTML = `
          <div class="flex justify-between items-start">
            <div>
              <p class="font-medium">${u.email}</p>
              <p class="text-xs text-gray-600">Role: <span class="font-semibold">${u.role}</span></p>
              <p class="text-xs text-gray-600">Companies: ${(u.allowed_companies || []).join(', ') || 'None'}</p>
            </div>
            <span class="text-xs text-gray-400">${u.created_at?.substring(0, 10) || ''}</span>
          </div>
        `;
        list.appendChild(div);
      });
      
      $('#kpi-users').textContent = data.users.length;
    } else {
      list.innerHTML = '<p class="text-sm text-gray-500 italic">No users found</p>';
    }
  } catch (err) {
    showToast('Failed to load users', true);
  }
}

$('#refresh-users')?.addEventListener('click', e => {
  e.preventDefault();
  refreshUsers();
});

$('#admin-create-user')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#admin-user-msg');
  msg.textContent = 'Creating...';
  const fd = new FormData(e.target);
  const payload = {
    email: fd.get('email'),
    password: fd.get('password'),
    companies: (fd.get('companies')||'').split(',').map(s=>s.trim()).filter(Boolean),
    role: fd.get('role')
  };
  try {
    const res = await authFetch(`${API_BASE}/auth/admin/create-user`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'Failed');
    msg.textContent = '✓ User created';
    msg.className = 'text-xs text-green-600';
    e.target.reset();
    refreshUsers();
    setTimeout(() => {msg.textContent = ''; msg.className = 'text-xs text-gray-500';}, 3000);
  } catch(err){ 
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
  }
});

$('#assign-company-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#assign-msg');
  msg.textContent = 'Assigning...';
  const fd = new FormData(e.target);
  const payload = { email: fd.get('email'), company: fd.get('company') };
  try {
    const res = await authFetch(`${API_BASE}/auth/admin/assign-company`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'Failed');
    msg.textContent = '✓ Assigned';
    msg.className = 'text-xs text-green-600';
    e.target.reset();
    refreshUsers();
    setTimeout(() => {msg.textContent = ''; msg.className = 'text-xs text-gray-500';}, 3000);
  } catch(err){ 
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
  }
});

$('#remove-company-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#remove-msg');
  msg.textContent = 'Removing...';
  const fd = new FormData(e.target);
  const payload = { email: fd.get('email'), company: fd.get('company') };
  try {
    const res = await authFetch(`${API_BASE}/auth/admin/remove-company`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'Failed');
    msg.textContent = '✓ Removed';
    msg.className = 'text-xs text-green-600';
    e.target.reset();
    refreshUsers();
    setTimeout(() => {msg.textContent = ''; msg.className = 'text-xs text-gray-500';}, 3000);
  } catch(err){ 
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
  }
});

$('#delete-user-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#delete-msg');
  msg.textContent = 'Deleting...';
  const fd = new FormData(e.target);
  const email = encodeURIComponent(fd.get('email'));
  try {
    const res = await authFetch(`${API_BASE}/auth/admin/user/${email}`, { method:'DELETE' });
    const data = await res.json();
    if(!res.ok) throw new Error(data.detail || 'Failed');
    msg.textContent = '✓ Deleted';
    msg.className = 'text-xs text-green-600';
    e.target.reset();
    refreshUsers();
    setTimeout(() => {msg.textContent = ''; msg.className = 'text-xs text-gray-500';}, 3000);
  } catch(err){ 
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
  }
});

// Initial load
refreshUsers();

/* ==================== DATA BROWSER ==================== */
async function loadDataBrowser() {
  const container = $('#company-browser');
  container.innerHTML = '<p class="text-sm text-gray-500 italic">Loading companies...</p>';
  
  let totalJobs = 0;
  let totalCVs = 0;
  
  try {
    const companiesRes = await authFetch(`${API_BASE}/companies/`);
    const { companies } = await companiesRes.json();
    
    container.innerHTML = '';
    
    if (!companies || companies.length === 0) {
      container.innerHTML = '<p class="text-sm text-gray-500 italic">No companies found</p>';
      return;
    }
    
    for (const company of companies) {
      // Get jobs for this company
      const jobsRes = await authFetch(`${API_BASE}/jobs/?company_name=${encodeURIComponent(company)}`);
      const { jobs } = await jobsRes.json();
      
      totalJobs += jobs.length;
      
      const companyDiv = document.createElement('div');
      companyDiv.className = 'border rounded-lg p-4 bg-gray-50';
      
      let jobsHTML = '';
      for (const job of jobs) {
        // Get CV count for each job
        try {
          const cvRes = await authFetch(`${API_BASE}/existing-cvs/?company_name=${encodeURIComponent(company)}&job_title=${encodeURIComponent(job)}`);
          const cvData = await cvRes.json();
          const cvCount = cvData.cvs?.length || 0;
          totalCVs += cvCount;
          
          jobsHTML += `
            <div class="flex justify-between items-center py-2 border-b last:border-0">
              <span class="text-sm">${job}</span>
              <span class="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">${cvCount} CVs</span>
            </div>
          `;
        } catch (e) {
          jobsHTML += `
            <div class="flex justify-between items-center py-2 border-b last:border-0">
              <span class="text-sm">${job}</span>
              <span class="text-xs bg-gray-100 text-gray-500 px-2 py-1 rounded">N/A</span>
            </div>
          `;
        }
      }
      
      companyDiv.innerHTML = `
        <div class="flex justify-between items-center mb-3">
          <h4 class="font-semibold text-lg text-gray-900">${company}</h4>
          <span class="text-sm text-gray-600">${jobs.length} jobs</span>
        </div>
        <div class="bg-white rounded p-3 space-y-1">
          ${jobsHTML || '<p class="text-xs text-gray-500 italic">No jobs</p>'}
        </div>
      `;
      
      container.appendChild(companyDiv);
    }
    
    $('#browser-total-companies').textContent = companies.length;
    $('#browser-total-jobs').textContent = totalJobs;
    $('#browser-total-cvs').textContent = totalCVs;
    
  } catch (err) {
    console.error('Failed to load data browser', err);
    container.innerHTML = '<p class="text-sm text-red-600">Error loading data</p>';
  }
}

$('#refresh-browser')?.addEventListener('click', e => {
  e.preventDefault();
  loadDataBrowser();
});

/* ==================== BULK OPERATIONS ==================== */
function loadBulkOpsDropdowns() {
  // Load companies into all bulk operation dropdowns
  const selectors = [
    '#bulk-delete-cvs select[name="company"]',
    '#bulk-delete-jds select[name="company"]',
    '#delete-company-form select[name="company"]'
  ];
  
  selectors.forEach(sel => {
    const select = $(sel);
    if (select) {
      select.innerHTML = '<option value="">Select Company</option>';
      allCompanies.forEach(c => select.appendChild(new Option(c, c)));
    }
  });
}

// Load jobs when company selected in bulk delete CVs
$('#bulk-delete-cvs select[name="company"]')?.addEventListener('change', async e => {
  const company = e.target.value;
  const jobSelect = $('#bulk-delete-cvs select[name="job"]');
  jobSelect.innerHTML = '<option value="">Loading...</option>';
  
  if (!company) {
    jobSelect.innerHTML = '<option value="">Select Job</option>';
    return;
  }
  
  try {
    const res = await authFetch(`${API_BASE}/jobs/?company_name=${encodeURIComponent(company)}`);
    const { jobs } = await res.json();
    jobSelect.innerHTML = '<option value="">Select Job</option>';
    jobs.forEach(j => jobSelect.appendChild(new Option(j, j)));
  } catch (err) {
    showToast('Failed to load jobs', true);
  }
});

// Load jobs when company selected in bulk delete JDs
$('#bulk-delete-jds select[name="company"]')?.addEventListener('change', async e => {
  const company = e.target.value;
  const jobSelect = $('#bulk-delete-jds select[name="job"]');
  jobSelect.innerHTML = '<option value="">Loading...</option>';
  
  if (!company) {
    jobSelect.innerHTML = '<option value="">All Jobs</option>';
    return;
  }
  
  try {
    const res = await authFetch(`${API_BASE}/jobs/?company_name=${encodeURIComponent(company)}`);
    const { jobs } = await res.json();
    jobSelect.innerHTML = '<option value="">All Jobs</option>';
    jobs.forEach(j => jobSelect.appendChild(new Option(j, j)));
  } catch (err) {
    showToast('Failed to load jobs', true);
  }
});

// Bulk delete CVs
$('#bulk-delete-cvs')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#bulk-cv-msg');
  const fd = new FormData(e.target);
  const company = fd.get('company');
  const job = fd.get('job');
  
  if (!confirm(`Delete ALL CVs for "${job}" at "${company}"? This cannot be undone.`)) return;
  
  msg.textContent = 'Deleting...';
  msg.className = 'text-xs text-blue-600';
  
  try {
    const res = await authFetch(`${API_BASE}/admin/bulk-delete-cvs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_name: company, job_title: job })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed');
    
    msg.textContent = `✓ Deleted ${data.deleted_count || 0} CVs`;
    msg.className = 'text-xs text-green-600';
    showToast('CVs deleted successfully');
    e.target.reset();
    setTimeout(() => { msg.textContent = ''; }, 5000);
  } catch (err) {
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
    showToast(err.message, true);
  }
});

// Bulk delete JDs
$('#bulk-delete-jds')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#bulk-jd-msg');
  const fd = new FormData(e.target);
  const company = fd.get('company');
  const job = fd.get('job') || null;
  
  const confirmMsg = job 
    ? `Delete JD for "${job}" at "${company}"?`
    : `Delete ALL JDs for "${company}"?`;
  
  if (!confirm(confirmMsg + ' This cannot be undone.')) return;
  
  msg.textContent = 'Deleting...';
  msg.className = 'text-xs text-blue-600';
  
  try {
    const res = await authFetch(`${API_BASE}/admin/bulk-delete-jds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_name: company, job_title: job })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed');
    
    msg.textContent = `✓ Deleted ${data.deleted_count || 0} JDs`;
    msg.className = 'text-xs text-green-600';
    showToast('JDs deleted successfully');
    e.target.reset();
    setTimeout(() => { msg.textContent = ''; }, 5000);
  } catch (err) {
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
    showToast(err.message, true);
  }
});

// Delete entire company
$('#delete-company-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#delete-company-msg');
  const fd = new FormData(e.target);
  const company = fd.get('company');
  const confirmName = fd.get('confirm_name');
  
  if (company !== confirmName) {
    msg.textContent = '✗ Company name does not match';
    msg.className = 'text-xs text-red-600';
    return;
  }
  
  if (!confirm(`FINAL WARNING: Delete ALL data for "${company}"? This is IRREVERSIBLE.`)) return;
  
  msg.textContent = 'Deleting entire company database...';
  msg.className = 'text-xs text-blue-600';
  
  try {
    const res = await authFetch(`${API_BASE}/admin/delete-company/${encodeURIComponent(company)}`, {
      method: 'DELETE'
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed');
    
    msg.textContent = `✓ Company deleted: ${data.message}`;
    msg.className = 'text-xs text-green-600';
    showToast('Company database deleted');
    e.target.reset();
    loadAllCompanies();
    setTimeout(() => { msg.textContent = ''; }, 5000);
  } catch (err) {
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
    showToast(err.message, true);
  }
});

/* ==================== MAINTENANCE ==================== */
function loadMaintenanceDropdowns() {
  const selectors = [
    '#reindex-form select[name="company"]',
    '#export-form select[name="company"]'
  ];
  
  selectors.forEach(sel => {
    const select = $(sel);
    if (select) {
      select.innerHTML = '<option value="">Select Company</option>';
      allCompanies.forEach(c => select.appendChild(new Option(c, c)));
    }
  });
}

// Reindex embeddings
$('#reindex-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#reindex-msg');
  const fd = new FormData(e.target);
  const company = fd.get('company');
  const type = fd.get('type');
  
  msg.textContent = 'Starting reindex... This may take a while.';
  msg.className = 'text-xs text-blue-600';
  
  try {
    const res = await authFetch(`${API_BASE}/admin/reindex`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_name: company, reindex_type: type })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed');
    
    msg.textContent = `✓ ${data.message}`;
    msg.className = 'text-xs text-green-600';
    showToast('Reindexing completed');
  } catch (err) {
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
    showToast(err.message, true);
  }
});

// Health check
$('#health-check-btn')?.addEventListener('click', async e => {
  const btn = e.target;
  const results = $('#health-results');
  
  btn.disabled = true;
  results.innerHTML = '<p class="text-sm text-gray-500 italic">Running health check...</p>';
  
  try {
    const res = await authFetch(`${API_BASE}/admin/health-check`);
    const data = await res.json();
    
    results.innerHTML = '';
    
    if (data.overall_status === 'healthy') {
      results.innerHTML += '<div class="bg-green-50 border border-green-200 p-3 rounded mb-2"><p class="text-sm text-green-700 font-semibold"><i class="fas fa-check-circle mr-2"></i>System Healthy</p></div>';
    } else {
      results.innerHTML += '<div class="bg-yellow-50 border border-yellow-200 p-3 rounded mb-2"><p class="text-sm text-yellow-700 font-semibold"><i class="fas fa-exclamation-triangle mr-2"></i>Issues Detected</p></div>';
    }
    
    // Display detailed results
    Object.entries(data.checks || {}).forEach(([key, value]) => {
      const status = value.status === 'ok' ? 'text-green-600' : 'text-red-600';
      const icon = value.status === 'ok' ? 'fa-check' : 'fa-times';
      results.innerHTML += `
        <div class="flex justify-between items-center py-2 border-b">
          <span class="text-sm">${key}</span>
          <span class="${status}"><i class="fas ${icon} mr-1"></i>${value.message || value.status}</span>
        </div>
      `;
    });
    
  } catch (err) {
    results.innerHTML = '<p class="text-sm text-red-600">Error running health check</p>';
    showToast('Health check failed', true);
  } finally {
    btn.disabled = false;
  }
});

// Export data
$('#export-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const msg = $('#export-msg');
  const fd = new FormData(e.target);
  const company = fd.get('company');
  const format = fd.get('format');
  
  msg.textContent = 'Preparing export...';
  msg.className = 'text-xs text-blue-600';
  
  try {
    const res = await authFetch(`${API_BASE}/admin/export/${encodeURIComponent(company)}?format=${format}`);
    
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || 'Export failed');
    }
    
    // Download file
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${company}_export_${new Date().toISOString().split('T')[0]}.${format}`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    msg.textContent = '✓ Export downloaded';
    msg.className = 'text-xs text-green-600';
    showToast('Data exported successfully');
    setTimeout(() => { msg.textContent = ''; }, 5000);
  } catch (err) {
    msg.textContent = '✗ ' + err.message;
    msg.className = 'text-xs text-red-600';
    showToast(err.message, true);
  }
});

/* ==================== ACTIVITY LOGS ==================== */
async function loadLogs() {
  // Populate company filter
  const companyFilter = $('#log-filter-company');
  if (companyFilter) {
    companyFilter.innerHTML = '<option value="">All Companies</option>';
    allCompanies.forEach(c => companyFilter.appendChild(new Option(c, c)));
  }
  
  // Load initial logs
  await fetchLogs();
}

async function fetchLogs() {
  const logsList = $('#logs-list');
  logsList.innerHTML = '<p class="text-sm text-gray-500 italic">Loading logs...</p>';
  
  const actionType = $('#log-filter-type')?.value || '';
  const company = $('#log-filter-company')?.value || '';
  const hours = $('#log-filter-time')?.value || '24';
  
  try {
    const params = new URLSearchParams();
    if (actionType) params.append('action_type', actionType);
    if (company) params.append('company', company);
    params.append('hours', hours);
    
    const res = await authFetch(`${API_BASE}/admin/logs?${params.toString()}`);
    const data = await res.json();
    
    logsList.innerHTML = '';
    
    if (!data.logs || data.logs.length === 0) {
      logsList.innerHTML = '<p class="text-sm text-gray-500 italic">No logs found</p>';
      return;
    }
    
    data.logs.forEach(log => {
      const div = document.createElement('div');
      const timestamp = new Date(log.timestamp).toLocaleString();
      const typeColor = {
        upload_cv: 'text-blue-600',
        upload_jd: 'text-green-600',
        search: 'text-purple-600',
        delete: 'text-red-600',
        error: 'text-red-700'
      }[log.action_type] || 'text-gray-600';
      
      div.className = 'bg-gray-50 p-3 rounded border text-xs';
      div.innerHTML = `
        <div class="flex justify-between items-start mb-1">
          <span class="${typeColor} font-semibold">${log.action_type.toUpperCase()}</span>
          <span class="text-gray-500">${timestamp}</span>
        </div>
        <p class="text-gray-700">${log.message}</p>
        ${log.user ? `<p class="text-gray-500 mt-1">User: ${log.user}</p>` : ''}
        ${log.company ? `<p class="text-gray-500">Company: ${log.company}</p>` : ''}
      `;
      logsList.appendChild(div);
    });
    
    // Update statistics
    $('#log-stat-uploads').textContent = data.stats?.uploads || 0;
    $('#log-stat-searches').textContent = data.stats?.searches || 0;
    $('#log-stat-users').textContent = data.stats?.active_users || 0;
    $('#log-stat-errors').textContent = data.stats?.errors || 0;
    
  } catch (err) {
    console.error('Failed to load logs', err);
    logsList.innerHTML = '<p class="text-sm text-red-600">Error loading logs</p>';
  }
}

$('#apply-log-filters')?.addEventListener('click', fetchLogs);
$('#refresh-logs')?.addEventListener('click', fetchLogs);

$('#export-logs')?.addEventListener('click', async () => {
  try {
    const res = await authFetch(`${API_BASE}/admin/logs/export`);
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `system_logs_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    showToast('Logs exported');
  } catch (err) {
    showToast('Export failed', true);
  }
});

/* ==================== CV MODAL ==================== */
const cvModal = $('#cv-modal');
const cvModalContent = $('#cv-modal-content');
const closeCvModal = $('#close-cv-modal');

// Close modal
closeCvModal?.addEventListener('click', () => {
  cvModal.classList.add('hidden');
});

// Close on background click
cvModal?.addEventListener('click', (e) => {
  if (e.target === cvModal) {
    cvModal.classList.add('hidden');
  }
});

// Handle View CV button clicks (event delegation)
document.addEventListener('click', async (e) => {
  if (e.target.closest('.view-cv-btn')) {
    const btn = e.target.closest('.view-cv-btn');
    const cvId = btn.dataset.cvId;
    await viewCV(cvId);
  }
});

async function viewCV(cvId) {
  // Show modal with loading state
  cvModal.classList.remove('hidden');
  cvModalContent.innerHTML = `
    <div class="text-center text-gray-500">
      <i class="fas fa-spinner fa-spin text-3xl mb-2"></i>
      <p>Loading CV...</p>
    </div>
  `;

  try {
    // Fetch CV data from MongoDB
    const res = await authFetch(`${API_BASE}/cv/${encodeURIComponent(currentCompany)}/${encodeURIComponent(currentJob)}/${encodeURIComponent(cvId)}`);
    
    if (!res.ok) {
      throw new Error('Failed to load CV');
    }

    const cvData = await res.json();
    
    // Display CV content
    cvModalContent.innerHTML = `
      <div class="space-y-6">
        <!-- Candidate Identifier Banner -->
        <div class="bg-blue-600 text-white p-4 rounded-lg -mt-2">
          <div class="flex items-center justify-between">
            <div>
              <h4 class="font-bold text-xl">${cvData.full_name || cvData.name || 'Candidate'}</h4>
              <p class="text-blue-100 text-lg mt-1">
                <i class="fas fa-envelope"></i> ${cvData.email || 'No email provided'}
              </p>
            </div>
            <div class="text-right text-sm">
              ${cvData.phone_number || cvData.phone ? `<p><i class="fas fa-phone"></i> ${cvData.phone_number || cvData.phone}</p>` : ''}
              ${cvData.location ? `<p><i class="fas fa-map-marker-alt"></i> ${cvData.location}</p>` : ''}
            </div>
          </div>
        </div>

        ${cvData.summary ? `
        <div class="bg-blue-50 p-4 rounded-lg">
          <h4 class="font-bold text-lg mb-2 text-gray-800">Professional Summary</h4>
          <p class="text-sm text-gray-700 whitespace-pre-wrap">${cvData.summary}</p>
        </div>
        ` : ''}

        ${cvData.skills && cvData.skills.length > 0 ? `
        <div class="bg-green-50 p-4 rounded-lg">
          <h4 class="font-bold text-lg mb-2 text-gray-800">Skills</h4>
          <div class="flex flex-wrap gap-2">
            ${cvData.skills.map(skill => `<span class="bg-green-200 text-green-800 text-xs px-2 py-1 rounded">${skill}</span>`).join('')}
          </div>
        </div>
        ` : ''}

        ${cvData.work_experience && cvData.work_experience.length > 0 ? `
        <div class="bg-purple-50 p-4 rounded-lg">
          <h4 class="font-bold text-lg mb-2 text-gray-800">Work Experience</h4>
          <div class="space-y-3">
            ${cvData.work_experience.map(exp => `
              <div class="border-l-4 border-purple-400 pl-3">
                <h5 class="font-semibold text-gray-800">${exp.job_title || 'N/A'}</h5>
                <p class="text-sm text-gray-600">${exp.company || 'N/A'} | ${exp.duration || 'N/A'}</p>
                ${exp.responsibilities ? `<p class="text-sm text-gray-700 mt-1 whitespace-pre-wrap">${exp.responsibilities}</p>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
        ` : ''}

        ${cvData.education && cvData.education.length > 0 ? `
        <div class="bg-yellow-50 p-4 rounded-lg">
          <h4 class="font-bold text-lg mb-2 text-gray-800">Education</h4>
          <div class="space-y-2">
            ${cvData.education.map(edu => `
              <div class="border-l-4 border-yellow-400 pl-3">
                <h5 class="font-semibold text-gray-800">${edu.degree || 'N/A'}</h5>
                <p class="text-sm text-gray-600">${edu.institution || 'N/A'} | ${edu.year || 'N/A'}</p>
              </div>
            `).join('')}
          </div>
        </div>
        ` : ''}

        ${cvData.certifications && cvData.certifications.length > 0 ? `
        <div class="bg-red-50 p-4 rounded-lg">
          <h4 class="font-bold text-lg mb-2 text-gray-800">Certifications</h4>
          <ul class="list-disc list-inside text-sm text-gray-700 space-y-1">
            ${cvData.certifications.map(cert => `<li>${cert}</li>`).join('')}
          </ul>
        </div>
        ` : ''}

        ${cvData.projects && cvData.projects.length > 0 ? `
        <div class="bg-indigo-50 p-4 rounded-lg">
          <h4 class="font-bold text-lg mb-2 text-gray-800">Projects</h4>
          <div class="space-y-2">
            ${cvData.projects.map(proj => `
              <div class="border-l-4 border-indigo-400 pl-3">
                <h5 class="font-semibold text-gray-800">${proj.name || 'Project'}</h5>
                ${proj.description ? `<p class="text-sm text-gray-700 whitespace-pre-wrap">${proj.description}</p>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
        ` : ''}
      </div>
    `;

  } catch (err) {
    console.error('[CV Modal] Error loading CV:', err);
    cvModalContent.innerHTML = `
      <div class="text-center text-red-600">
        <i class="fas fa-exclamation-circle text-3xl mb-2"></i>
        <p class="font-medium">Failed to load CV</p>
        <p class="text-sm text-gray-600">${err.message}</p>
      </div>
    `;
  }
}

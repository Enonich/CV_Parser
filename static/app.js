/* ==================== CONFIG ==================== */
const API_BASE = 'http://localhost:8000';   // <-- change if your backend runs elsewhere
let currentCompany = '', currentJob = '';

/* ==================== AUTH BOOTSTRAP ==================== */
const AUTH_TOKEN_KEY = 'auth_token';
let userRole = 'user';
let userCompany = null;
let allowedCompanies = [];

function getAuthToken() { return localStorage.getItem(AUTH_TOKEN_KEY); }

function requireAuth() { 
  if(!getAuthToken()) { 
    window.location.href = '/static/login.html';
    return false;
  }
  return true;
}

// Check auth before page loads
if (!requireAuth()) {
  // Exit early if no token
} else {
  // Token exists, will verify with server
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
    // Token invalid or expired
    localStorage.removeItem(AUTH_TOKEN_KEY);
    window.location.href = '/static/login.html';
    return resp; // navigation in progress
  }
  return resp;
}

// Populate user info and setup UI based on role
(async function initUserInfo(){
  try {
    console.log('[Auth] Checking authentication...');
    const r = await authFetch(`${API_BASE}/auth/me`);
    if(r.ok) {
      const me = await r.json();
      console.log('[Auth] Authentication successful:', me.email);
      userRole = me.role;
      allowedCompanies = me.allowed_companies || [];
      userCompany = allowedCompanies.length > 0 ? allowedCompanies[0] : null;
      
      const el = document.getElementById('user-info');
      if (el) { 
        el.textContent = `${me.email} ${userRole === 'admin' ? '(Admin)' : ''}`;
        el.classList.remove('hidden'); 
      }
      
      // Show page BEFORE setup functions to ensure it's always visible
      console.log('[Auth] Revealing page...');
      document.body.classList.remove('auth-checking');
      
      if (userRole === 'admin') {
        document.getElementById('admin-tab-link')?.classList.remove('hidden');
        document.getElementById('admin-tab-side')?.classList.remove('hidden');
        setupAdminConsole();
        setupAdminDashboard();
      } else {
        // Regular user - set up their company context
        if (userCompany) {
          currentCompany = userCompany;
          setupUserDashboard();
        } else {
          showToast('No company assigned. Contact admin.', true);
        }
      }
    } else {
      // Auth failed, redirect will happen in authFetch
      console.log('[Auth] Authentication failed, redirecting to login');
      window.location.href = '/static/login.html';
    }
  } catch(e){ 
    console.error('[Auth] Error during authentication:', e);
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
  const p = document.createElement('p');
  p.textContent = `${new Date().toLocaleTimeString()} — ${msg}`;
  log.insertBefore(p, log.firstChild);
}

function updateContextDisplay() {
  if (currentCompany && currentJob) {
    const companyEl = $('#current-company');
    const jobEl = $('#current-job');
    const contextEl = $('#context-display');
    
    if (companyEl) companyEl.textContent = currentCompany;
    if (jobEl) jobEl.textContent = currentJob;
    if (contextEl) contextEl.classList.remove('hidden');
  }
}

/* ==================== DASHBOARD SETUP ==================== */
function setupUserDashboard() {
  // For regular users: auto-load their company data
  $('#dash-company').textContent = userCompany;
  $('#change-context').style.display = 'none'; // Users can't change company
  
  // Set hidden company fields in upload forms
  const hiddenCvCompany = document.getElementById('hidden-company-name');
  const hiddenJdCompany = document.getElementById('hidden-jd-company-name');
  if (hiddenCvCompany) hiddenCvCompany.value = userCompany;
  if (hiddenJdCompany) hiddenJdCompany.value = userCompany;
  
  // Show admin link button for admins
  const adminBtn = document.getElementById('admin-link-btn');
  if (userRole === 'admin' && adminBtn) {
    adminBtn.classList.remove('hidden');
    adminBtn.addEventListener('click', () => {
      window.location.href = '/static/admin.html';
    });
  }
  
  // Highlight dashboard tab on initial load
  $$('.tab-link').forEach(l => {
    if (l.dataset.tab === 'dashboard') {
      l.classList.add('text-blue-700', 'font-medium');
      l.classList.remove('text-gray-600');
    }
  });
  
  // Load available jobs for this company
  loadUserJobs();
  
  // Load initial dashboard
  loadDashboard();
}

function setupAdminDashboard() {
  // Admin should go to admin.html instead
  window.location.href = '/static/admin.html';
}

async function loadUserJobs() {
  try {
    const res = await authFetch(`${API_BASE}/jobs/?company_name=${encodeURIComponent(userCompany)}`);
    const { jobs } = await res.json();
    
    if (jobs && jobs.length > 0) {
      // Store jobs globally
      window.userJobs = jobs;
      
      // Update jobs count
      $('#jobs-count').textContent = `${jobs.length} role${jobs.length !== 1 ? 's' : ''}`;
      
      // Create job cards in dashboard
      const jobsGrid = $('#jobs-grid');
      jobsGrid.innerHTML = '';
      
      jobs.forEach(async (jobTitle) => {
        // Get data status for each job
        const statusRes = await authFetch(`${API_BASE}/data-status/?company_name=${encodeURIComponent(userCompany)}&job_title=${encodeURIComponent(jobTitle)}`);
        const statusData = await statusRes.json();
        
        const card = document.createElement('div');
        card.className = 'bg-white rounded-lg shadow-sm border p-4 cursor-pointer hover:shadow-md hover:border-blue-500 transition-all';
        card.dataset.jobTitle = jobTitle;
        
        const hasJD = statusData.jd_exists;
        const cvCount = statusData.cv_count || 0;
        
        card.innerHTML = `
          <div class="flex justify-between items-start mb-3">
            <div class="flex-1">
              <h4 class="font-semibold text-gray-900 mb-1">${jobTitle}</h4>
              <p class="text-xs text-gray-500">${userCompany}</p>
            </div>
            ${statusData.can_search ? 
              '<span class="text-green-600 text-xs"><i class="fas fa-check-circle"></i> Ready</span>' : 
              '<span class="text-yellow-600 text-xs"><i class="fas fa-exclamation-circle"></i> Incomplete</span>'}
          </div>
          <div class="flex items-center justify-between text-sm">
            <div class="flex items-center space-x-4">
              <div class="flex items-center space-x-1">
                <i class="fas fa-file-alt text-gray-400"></i>
                <span class="text-gray-600">${cvCount} CVs</span>
              </div>
              <div class="flex items-center space-x-1">
                <i class="fas fa-briefcase ${hasJD ? 'text-green-600' : 'text-gray-400'}"></i>
                <span class="text-gray-600">${hasJD ? 'JD Added' : 'No JD'}</span>
              </div>
            </div>
            <button class="text-blue-600 hover:text-blue-800 text-xs">
              View <i class="fas fa-arrow-right ml-1"></i>
            </button>
          </div>
        `;
        
        // Click handler to show job details
        card.addEventListener('click', () => {
          selectJob(jobTitle);
        });
        
        jobsGrid.appendChild(card);
      });
      
      // Populate datalists for autocomplete in upload forms
      const cvDatalist = document.getElementById('job-titles-list');
      const jdDatalist = document.getElementById('jd-job-titles-list');
      const searchJobSelect = document.getElementById('search-job');
      
      if (cvDatalist) {
        cvDatalist.innerHTML = '';
        jobs.forEach(j => {
          const option = document.createElement('option');
          option.value = j;
          cvDatalist.appendChild(option);
        });
      }
      
      if (jdDatalist) {
        jdDatalist.innerHTML = '';
        jobs.forEach(j => {
          const option = document.createElement('option');
          option.value = j;
          jdDatalist.appendChild(option);
        });
      }
      
      // Populate search job dropdown
      if (searchJobSelect) {
        searchJobSelect.innerHTML = '<option value="">Select Job Title</option>';
        jobs.forEach(j => {
          const opt = document.createElement('option');
          opt.value = j;
          opt.textContent = j;
          searchJobSelect.appendChild(opt);
        });
      }
    } else {
      $('#jobs-grid').innerHTML = '<p class="text-sm text-gray-500 italic col-span-full">No jobs yet - upload a JD to start</p>';
    }
  } catch (err) {
    console.error('Failed to load jobs', err);
    $('#jobs-grid').innerHTML = '<p class="text-sm text-red-600 italic col-span-full">Failed to load jobs</p>';
  }
}

/* ==================== SELECT JOB ==================== */
function selectJob(jobTitle) {
  currentJob = jobTitle;
  $('#selected-job-title').textContent = jobTitle;
  $('#dash-job-inline').textContent = ` • ${jobTitle}`;
  
  // Hide jobs grid, show job details
  $('#jobs-section').classList.add('hidden');
  $('#job-details-section').classList.remove('hidden');
  
  // Load job details
  refreshDashboard();
}

// Close job details button
$('#close-job-details')?.addEventListener('click', () => {
  currentJob = '';
  $('#dash-job-inline').textContent = '';
  $('#job-details-section').classList.add('hidden');
  $('#jobs-section').classList.remove('hidden');
  
  // Reload jobs to refresh status
  loadUserJobs();
});

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
    // loadCompanies not needed for users - jobs already loaded
  });
});

/* ==================== DRAG & DROP ==================== */
function setupDropzone(zoneId) {
  const zone = $(`#${zoneId}`);
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

/* ==================== JD TAB SWITCHING ==================== */
// Tab switching for JD upload vs text input
$('#jd-upload-tab').addEventListener('click', () => {
  $('#jd-upload-tab').classList.add('text-blue-700', 'border-b-2', 'border-blue-700');
  $('#jd-upload-tab').classList.remove('text-gray-600');
  $('#jd-text-tab').classList.remove('text-blue-700', 'border-b-2', 'border-blue-700');
  $('#jd-text-tab').classList.add('text-gray-600');
  $('#jd-upload-section').classList.remove('hidden');
  $('#jd-text-section').classList.add('hidden');
  $('#jd-text-input').removeAttribute('required');
  const fileInput = $('#jd-dropzone input[type="file"]');
  if (fileInput) fileInput.setAttribute('required', 'required');
});

$('#jd-text-tab').addEventListener('click', () => {
  $('#jd-text-tab').classList.add('text-blue-700', 'border-b-2', 'border-blue-700');
  $('#jd-text-tab').classList.remove('text-gray-600');
  $('#jd-upload-tab').classList.remove('text-blue-700', 'border-b-2', 'border-blue-700');
  $('#jd-upload-tab').classList.add('text-gray-600');
  $('#jd-text-section').classList.remove('hidden');
  $('#jd-upload-section').classList.add('hidden');
  $('#jd-text-input').setAttribute('required', 'required');
  const fileInput = $('#jd-dropzone input[type="file"]');
  if (fileInput) fileInput.removeAttribute('required');
});

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
$('#cv-form').addEventListener('submit', async e => {
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

  const company = userCompany || form.querySelector('input[name="company_name"]').value;
  const job = form.querySelector('input[name="job_title"]').value;

  // Validate that job title is not empty and not the same as company name
  if (!job || !job.trim()) {
    showToast('Please enter a job title', true);
    return;
  }
  
  if (job.toLowerCase().trim() === company.toLowerCase().trim()) {
    showToast('Job title cannot be the same as company name. Please enter a specific job role (e.g., "Software Engineer", "Data Analyst")', true);
    return;
  }

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
        const errorMsg = data.message || data.detail || 'Upload failed';
        console.error(`[CV Upload] Failed to upload ${file.name}:`, errorMsg);
        // Show individual error for critical failures
        if (data.error_code === 'missing_identifier') {
          showToast(`${file.name}: ${errorMsg}`, true);
        }
      } else if (data.status === 'error') {
        // Backend returned 200 but with error status (shouldn't happen after our fix, but defensive)
        errorCount++;
        const errorMsg = data.message || 'Database save failed';
        console.error(`[CV Upload] ${file.name} processing error:`, errorMsg);
        showToast(`${file.name}: ${errorMsg}`, true);
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
      showToast(`${file.name}: Network or server error`, true);
    }
  }

  currentCompany = company;
  currentJob = job;
  updateContextDisplay();

  // Show summary
  let message = `Upload complete: ${successCount} successful`;
  if (duplicateCount > 0) message += `, ${duplicateCount} duplicates`;
  if (errorCount > 0) message += `, ${errorCount} errors`;
  
  showToast(message, errorCount > 0);
  addActivity(`Uploaded ${successCount} CVs for ${job}`);
  
  if (userRole !== 'admin') loadUserJobs();
  loadDashboard();
  form.reset();
  $('#cv-file-info').classList.add('hidden');
  $('#cv-file-list').innerHTML = '';
  $('#cv-file-count').textContent = '0';
  progressDiv.classList.add('hidden');
  progressBar.style.width = '0%';
  
  submitBtn.disabled = false;
  spinner.classList.add('hidden');
  text.textContent = 'Parse & Save CVs';
  
  $('.tab-link[data-tab="dashboard"]').click();
});

/* ==================== UPLOAD JD ==================== */
$('#jd-form').addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const submitBtn = form.querySelector('button[type="submit"]');
  const spinner = $('#jd-spinner');
  const text = $('#jd-submit-text');

  // Validate job title before proceeding
  const company = userCompany || form.querySelector('input[name="company_name"]').value;
  const job = form.querySelector('input[name="job_title"]').value;
  
  if (!job || !job.trim()) {
    showToast('Please enter a job title', true);
    return;
  }
  
  if (job.toLowerCase().trim() === company.toLowerCase().trim()) {
    showToast('Job title cannot be the same as company name. Please enter a specific job role (e.g., "Software Engineer", "Data Analyst")', true);
    return;
  }

  submitBtn.disabled = true;
  spinner.classList.remove('hidden');
  text.textContent = 'Saving...';

  // Check if text mode is active
  const isTextMode = !$('#jd-text-section').classList.contains('hidden');
  
  const formData = new FormData(form);
  
  // If in text mode, remove file and add text flag
  if (isTextMode) {
    formData.delete('file');
    const jdText = $('#jd-text-input').value.trim();
    if (!jdText) {
      showToast('Please enter job description text', true);
      submitBtn.disabled = false;
      spinner.classList.add('hidden');
      text.textContent = 'Save JD';
      return;
    }
    formData.append('jd_text', jdText);
  } else {
    // File mode - check if file is selected
    const fileInput = $('#jd-dropzone input[type="file"]');
    if (!fileInput.files.length) {
      showToast('Please select a file', true);
      submitBtn.disabled = false;
      spinner.classList.add('hidden');
      text.textContent = 'Save JD';
      return;
    }
  }

  try {
    const res = await authFetch(`${API_BASE}/upload-jd/`, { method: 'POST', body: formData });
    const data = await res.json();
    
    console.log(`[JD Upload] Response status: ${res.status}`, data);
    
    if (!res.ok) {
      const errorMsg = data.message || data.detail || 'JD upload failed';
      console.error(`[JD Upload] Failed:`, errorMsg);
      throw new Error(errorMsg);
    }
    
    if (data.status === 'error') {
      // Backend returned 200 but with error status (shouldn't happen after our fix, but defensive)
      const errorMsg = data.message || 'Database save failed';
      console.error(`[JD Upload] Processing error:`, errorMsg);
      throw new Error(errorMsg);
    }

    currentCompany = formData.get('company_name');
    currentJob = formData.get('job_title');
    updateContextDisplay();

    if (data.existing) {
      showToast('JD already exists');
    } else {
      showToast('JD saved successfully!');
      addActivity(`Uploaded JD: ${currentJob}`);
    }
    if (userRole !== 'admin') loadUserJobs(); // Refresh job list for users
    loadDashboard();
    
    // Reset form and switch back to upload tab
    form.reset();
    $('#jd-upload-tab').click();
    $('#jd-file-info').classList.add('hidden');
    
    $('.tab-link[data-tab="dashboard"]').click();
  } catch (err) {
    console.error('[JD Upload] Error:', err);
    showToast(err.message, true);
  } finally {
    submitBtn.disabled = false;
    spinner.classList.add('hidden');
    text.textContent = 'Save JD';
  }
});

/* ==================== SEARCH & RANK ==================== */
async function loadCompanies() {
  try {
    if (userRole !== 'admin') {
      // Regular users only see their company
      const select = $('#search-company');
      select.innerHTML = `<option value="${userCompany}">${userCompany}</option>`;
      select.value = userCompany;
      select.disabled = true;
      // Trigger job loading
      const event = new Event('change');
      select.dispatchEvent(event);
    } else {
      // Admin can see all companies
      const res = await authFetch(`${API_BASE}/auth/my-companies`);
      const data = await res.json();
      const companies = data.companies || [];
      const select = $('#search-company');
      select.innerHTML = '<option value="">Select Company</option>';
      companies.forEach(c => select.appendChild(new Option(c, c)));
    }
  } catch (err) {
    showToast('Failed to load companies', true);
  }
}

/* ==================== SEARCH & RANK ==================== */
console.log('[Init] Setting up search functionality for user...');
console.log('[Init] User company:', userCompany);

const searchBtn = $('#search-btn');
const searchCompanySelect = $('#search-company');

console.log('[Init] Search button:', searchBtn);
console.log('[Init] Search company select:', searchCompanySelect);

// Disable search button by default until data is verified
if (searchBtn) {
  searchBtn.disabled = true;
  searchBtn.title = 'Please select a job title first';
}

// Admin users have company selector, regular users don't
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

// Add job selection change handler to check data status
const searchJobSelect = $('#search-job');
if (searchJobSelect) {
  searchJobSelect.addEventListener('change', async e => {
    const job = e.target.value;
    const company = searchCompanySelect ? searchCompanySelect.value : userCompany;
    
    if (!job || !company) {
      if (searchBtn) {
        searchBtn.disabled = true;
        searchBtn.title = 'Please select a job title';
      }
      return;
    }
    
    // Check if data exists for this job
    try {
      console.log('[Data Status] Checking for company:', company, 'job:', job);
      const res = await authFetch(`${API_BASE}/data-status/?company_name=${encodeURIComponent(company)}&job_title=${encodeURIComponent(job)}`);
      const status = await res.json();
      
      console.log('[Data Status] Response:', status);
      
      if (searchBtn) {
        if (status.can_search) {
          searchBtn.disabled = false;
          searchBtn.title = `Search ${status.cv_count} CVs`;
          console.log('[Data Status] Search enabled - CVs:', status.cv_count, 'JD:', status.jd_exists);
        } else {
          searchBtn.disabled = true;
          if (!status.jd_exists && status.cv_count === 0) {
            searchBtn.title = 'Please upload CVs and Job Description first';
          } else if (!status.jd_exists) {
            searchBtn.title = 'Please upload Job Description first';
          } else if (status.cv_count === 0) {
            searchBtn.title = 'Please upload CVs first';
          }
          console.log('[Data Status] Search disabled -', searchBtn.title);
        }
      }
    } catch (err) {
      console.error('[Data Status] Error checking status:', err);
      if (searchBtn) {
        searchBtn.disabled = true;
        searchBtn.title = 'Error checking data status';
      }
    }
  });
}

if (searchBtn) {
  console.log('[Init] Adding click listener to search button');
  
  let isSearching = false; // Prevent double-clicks
  
  searchBtn.addEventListener('click', async () => {
    console.log('[Search] Button clicked!');
    
    // Prevent multiple simultaneous searches
    if (isSearching) {
      console.log('[Search] Already searching, ignoring click');
      return;
    }
    
    // For regular users, company comes from their account; for admins, from select
    const company = searchCompanySelect ? searchCompanySelect.value : userCompany;
    const job = $('#search-job').value;
    
    console.log('[Search] Company:', company, 'Job:', job);
  
    if (!company) {
      return showToast('No company assigned. Contact admin.', true);
    }
    
    if (!job) {
      return showToast('Please select a job title', true);
    }

    const btn = $('#search-btn');
    const spinner = $('#search-spinner');
    const btnText = btn.querySelector('span');
    const originalText = btnText.textContent;
    
    // Get the top_k value from the input field
    const topKInput = $('#search-top-k');
    let topK = parseInt(topKInput.value) || 10;
    if (topK < 1) topK = 1;
    if (topK > 100) topK = 100;
    
    // Mark as searching
    isSearching = true;
    btn.disabled = true;
    spinner.classList.remove('hidden');
    btnText.textContent = 'Embedding & Searching...';

    console.log(`[Search] Starting search for company: ${company}, job: ${job}, top_k: ${topK}`);

    try {
      const res = await authFetch(`${API_BASE}/search-cvs/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_name: company, job_title: job, top_k_cvs: topK, show_details: true })
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
          const displayName = r.name || r.original_identifier || r.cv_id;
          const displayContact = (r.name && r.original_identifier) ? ` (${r.original_identifier})` : '';
          console.log(`  ${idx + 1}. ${displayName}${displayContact}`);
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
      updateContextDisplay();
      displayResults(data.results);
      const lastSearchEl = $('#last-search');
      if (lastSearchEl) {
        lastSearchEl.textContent = `${data.results.length} results`;
      }
      addActivity(`Searched CVs for ${job} - Found ${data.results.length} matches`);
      showToast(`Found ${data.results.length} matching CVs`);
      
    } catch (err) {
      console.error(`[Search] Exception:`, err);
      showToast(`Search error: ${err.message}`, true);
    } finally {
      isSearching = false;
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
    
    // Display name prominently, then email/phone
    const displayName = r.name || r.original_identifier || 'Unknown Candidate';
    const displayContact = (r.name && r.original_identifier) ? r.original_identifier : '';
    
    card.innerHTML = `
      <div class="flex justify-between items-start mb-4">
        <div class="flex-1">
          <h4 class="font-semibold text-lg">${displayName}</h4>
          ${displayContact ? `<p class="text-sm text-gray-700 mt-1"><i class="fas fa-envelope"></i> ${displayContact}</p>` : ''}
          <p class="text-xs text-gray-500 mt-1">CV ID: ${r.cv_id}</p>
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
      <div class="mb-2">
        <h5 class="font-medium text-sm text-gray-700 mb-2 flex items-center gap-2">Section Performance
          <span class="text-[10px] font-normal text-gray-400">(bars scaled 0–100%)</span>
        </h5>
        <div class="w-full overflow-x-auto">
          <canvas id="bar-chart-${index}" height="170"></canvas>
        </div>
      </div>
    `;
    container.appendChild(card);
    // Build bar chart
    const sectionScores = r.section_scores || {};
    const labels = Object.keys(sectionScores);
    const dataVals = labels.map(k => parseFloat(((sectionScores[k] || 0) * 100).toFixed(2))); // convert to percentage

    if (!labels.length) {
      const wrap = card.querySelector('h5').parentElement;
      wrap.innerHTML += '<p class="text-xs text-gray-500 italic">No section scores</p>';
      return;
    }

    const ctx = document.getElementById(`bar-chart-${index}`).getContext('2d');

    // Generate elegant gradients per bar based on value
    const gradientColors = dataVals.map(val => {
      const g = ctx.createLinearGradient(0, 0, 0, 160);
      if (val >= 75) { // green scale
        g.addColorStop(0, 'rgba(16, 185, 129, 0.9)');
        g.addColorStop(1, 'rgba(16, 185, 129, 0.3)');
      } else if (val >= 50) { // amber scale
        g.addColorStop(0, 'rgba(245, 158, 11, 0.9)');
        g.addColorStop(1, 'rgba(245, 158, 11, 0.3)');
      } else { // red scale
        g.addColorStop(0, 'rgba(220, 38, 38, 0.9)');
        g.addColorStop(1, 'rgba(220, 38, 38, 0.25)');
      }
      return g;
    });

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels.map(l => l.replace(/_/g, ' ')),
        datasets: [{
          label: 'Section Score (%)',
          data: dataVals,
          backgroundColor: gradientColors,
          borderColor: dataVals.map(v => v >= 75 ? '#059669' : v >= 50 ? '#d97706' : '#b91c1c'),
          borderWidth: 1,
          borderRadius: 6,
          maxBarThickness: 40
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 900,
          easing: 'easeOutQuart'
        },
        scales: {
          y: {
            beginAtZero: true,
            suggestedMax: 100,
            ticks: {
              callback: v => v + '%',
              font: { size: 10 }
            },
            grid: { color: 'rgba(0,0,0,0.05)' }
          },
          x: {
            ticks: {
              font: { size: 10 },
              callback: function(val) {
                const label = this.getLabelForValue(val);
                return label.length > 14 ? label.slice(0, 12) + '…' : label;
              }
            },
            grid: { display: false }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.label}: ${ctx.parsed.y.toFixed(1)}%`
            }
          },
          datalabels: {
            anchor: 'end',
            align: 'start',
            offset: -4,
            color: '#111827',
            formatter: v => v.toFixed(0) + '%',
            font: { size: 10, weight: '600' }
          }
        },
        layout: { padding: { top: 8 } },
        interaction: { mode: 'index', intersect: false }
      }
    });
  });
}

/* ==================== DASHBOARD ==================== */
async function loadDashboard() {
  // Check if user has company assigned
  if (!userCompany) {
    showEmptyDashboard('No company assigned');
    return;
  }

  // If no job selected, show company-level statistics
  if (!currentJob) {
    await loadCompanyDashboard();
    return;
  }

  // Load job-specific dashboard
  await loadJobDashboard();
}

function showEmptyDashboard(message) {
  $('#kpi-cvs').textContent = '0';
  $('#kpi-top').textContent = '–';
  $('#kpi-avg').textContent = '–';
  $('#kpi-new').textContent = '0';
  $('#top-candidates').innerHTML = `<p class="text-sm text-gray-500 italic">${message}</p>`;
}

async function loadCompanyDashboard() {
  try {
    // Load all jobs for the company
    const jobsRes = await authFetch(`${API_BASE}/jobs/?company_name=${encodeURIComponent(userCompany)}`);
    const jobsData = await jobsRes.json();
    const jobs = jobsData.jobs || [];

    if (jobs.length === 0) {
      showEmptyDashboard('No jobs found - upload a JD to start');
      return;
    }

    // Get total CVs across all jobs
    let totalCVs = 0;
    for (const job of jobs) {
      const cvRes = await authFetch(`${API_BASE}/existing-cvs/?company_name=${encodeURIComponent(userCompany)}&job_title=${encodeURIComponent(job)}`);
      if (cvRes.ok) {
        const cvData = await cvRes.json();
        totalCVs += (cvData.cvs || []).length;
      }
    }

    $('#kpi-cvs').textContent = totalCVs;
    $('#kpi-top').textContent = jobs.length;
    $('#kpi-avg').textContent = '–';
    $('#kpi-new').textContent = '0';
    $('#top-candidates').innerHTML = `<p class="text-sm text-gray-500 italic">Select a job title to see rankings</p>`;
    
    addActivity(`Company dashboard loaded: ${jobs.length} jobs, ${totalCVs} CVs`);
  } catch (err) {
    console.error('Failed to load company dashboard', err);
    showEmptyDashboard('Database not found or error loading data');
  }
}

async function loadJobDashboard() {
  try {
    // Get CV count for this job
    const cvRes = await authFetch(`${API_BASE}/existing-cvs/?company_name=${encodeURIComponent(userCompany)}&job_title=${encodeURIComponent(currentJob)}`);
    
    if (!cvRes.ok) {
      showEmptyDashboard('No data found for this job');
      return;
    }

    const cvData = await cvRes.json();
    const cvs = cvData.cvs || [];
    $('#kpi-cvs').textContent = cvs.length;

    if (cvs.length === 0) {
      $('#kpi-top').textContent = '–';
      $('#kpi-avg').textContent = '–';
      $('#kpi-new').textContent = '0';
      $('#top-candidates').innerHTML = '<p class="text-sm text-gray-500 italic">No CVs uploaded for this job yet</p>';
      return;
    }

    // Run search to get ranked results
    const searchRes = await authFetch(`${API_BASE}/search-cvs/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_name: userCompany,
        job_title: currentJob,
        top_k_cvs: 5,
        show_details: true
      })
    });

    if (!searchRes.ok) {
      showEmptyDashboard('Error ranking CVs');
      return;
    }

    const searchData = await searchRes.json();
    const results = searchData.results || [];

    // KPI: Top Match
    if (results.length > 0) {
      const topScoreRaw = (results[0].combined_score || results[0].total_score || 0);
      const topScorePct = (topScoreRaw * 100).toFixed(1);
      $('#kpi-top').textContent = `${topScorePct}%`;
    } else {
      $('#kpi-top').textContent = '–';
    }

    // KPI: Average Score
    if (results.length > 0) {
      const avgRaw = results.reduce((sum, r) => sum + (r.combined_score || r.total_score || 0), 0) / results.length;
      $('#kpi-avg').textContent = `${(avgRaw * 100).toFixed(1)}%`;
    } else {
      $('#kpi-avg').textContent = '–';
    }

    // KPI: New Today (placeholder - would need timestamps)
    $('#kpi-new').textContent = '0';

    // Display top candidates
    const container = $('#top-candidates');
    container.innerHTML = '';
    
    if (results.length > 0) {
      results.slice(0, 5).forEach((r, i) => {
  const scorePct = ((r.combined_score || r.total_score || 0) * 100).toFixed(2);
        const displayName = r.name || r.original_identifier || r.cv_id;
        const div = document.createElement('div');
        div.className = 'flex justify-between items-center py-2 border-b';
        div.innerHTML = `
          <div class="flex items-center space-x-3">
            <span class="font-bold text-blue-700">#${i+1}</span>
            <span class="text-sm font-medium">${displayName}</span>
            ${r.original_identifier && r.name ? `<span class="text-xs text-gray-500">${r.original_identifier}</span>` : ''}
          </div>
          <span class="font-semibold text-green-700">${scorePct}%</span>
        `;
        container.appendChild(div);
      });
    } else {
      container.innerHTML = '<p class="text-sm text-gray-500 italic">No rankings available</p>';
    }

    addActivity(`Loaded dashboard for ${currentJob}: ${cvs.length} CVs`);
  } catch (err) {
    console.error('Failed to load job dashboard', err);
    showEmptyDashboard('Error loading dashboard data');
  }
}

/* Refresh context button */
$('#change-context')?.addEventListener('click', () => {
  loadDashboard();
  showToast('Dashboard refreshed');
});

/* ==================== INIT ==================== */
/* ==================== DASHBOARD INTELLIGENCE ==================== */
async function refreshDashboard() {
  if (!currentCompany || !currentJob) {
    // Show jobs grid instead of details
    $('#jobs-section').classList.remove('hidden');
    $('#job-details-section').classList.add('hidden');
    return;
  }

  $('#dash-company').textContent = currentCompany;
  $('#selected-job-title').textContent = currentJob;

  try {
    // 1. Get CV count
    const cvRes = await authFetch(`${API_BASE}/existing-cvs/?company_name=${currentCompany}&job_title=${currentJob}`);
    const cvData = cvRes.ok ? await cvRes.json() : { cvs: [] };
    const cvs = cvData.cvs || [];
    $('#kpi-cvs').textContent = cvs.length;

    // 2. Run search to get scores
    const searchRes = await authFetch(`${API_BASE}/search-cvs/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company_name: currentCompany,
        job_title: currentJob,
        top_k_cvs: 50,
        show_details: true
      })
    });

    if (!searchRes.ok) throw new Error('Search failed');

    const searchData = await searchRes.json();
    const results = searchData.results || [];

    // KPI: Top Match
    if (results.length > 0) {
      const top = results[0];
  const topScoreRaw = (top.combined_score || top.total_score || 0);
  $('#kpi-top').textContent = `${(topScoreRaw * 100).toFixed(1)}%`;
      $('#kpi-top').className = 'text-3xl font-bold text-green-700';
    }

    // KPI: Avg Score
    if (results.length > 0) {
  const avgRaw = results.reduce((sum, r) => sum + (r.combined_score || r.total_score || 0), 0) / results.length;
  const avgScorePct = (avgRaw * 100).toFixed(1);
  $('#kpi-avg').textContent = `${avgScorePct}%`;
      $('#kpi-avg').className = 'text-3xl font-bold text-blue-700';
    }

    // KPI: New Today
    const today = new Date().toISOString().split('T')[0];
    const newToday = cvs.filter(cv => {
      const date = cv.upload_date || cv._id?.substring(0, 8);
      return date === today || (date && date >= today);
    }).length;
    $('#kpi-new').textContent = newToday;

    // Top 5 Candidates
    const container = $('#top-candidates');
    container.innerHTML = '';
    results.slice(0, 5).forEach((r, i) => {
  const scorePct = ((r.combined_score || r.total_score || 0) * 100).toFixed(1);
      const displayName = r.name || r.original_identifier || r.cv_id;
      const displayContact = (r.name && r.original_identifier) ? r.original_identifier : '';
      const card = document.createElement('div');
      card.className = 'flex justify-between items-center p-3 bg-gray-50 rounded-lg';
      card.innerHTML = `
        <div class="flex items-center space-x-3">
          <div class="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center text-sm font-bold">
            ${i + 1}
          </div>
          <div>
            <p class="font-medium">${displayName}</p>
            ${displayContact ? `<p class="text-xs text-gray-600"><i class="fas fa-envelope"></i> ${displayContact}</p>` : ''}
            <p class="text-xs text-gray-400">ID: ${r.cv_id.slice(-8)}</p>
          </div>
        </div>
        <div class="text-right">
          <p class="text-lg font-bold text-blue-700">${scorePct}%</p>
          <p class="text-xs text-gray-500">Match</p>
        </div>
      `;
      container.appendChild(card);
    });

  } catch (err) {
    console.error('Dashboard refresh failed:', err);
    $('#top-candidates').innerHTML = '<p class="text-sm text-red-600">Failed to load rankings</p>';
  }
}

// Replace old loadDashboard()
async function loadDashboard() {
  if (!currentJob) {
    // Show jobs grid when no job is selected
    $('#jobs-section').classList.remove('hidden');
    $('#job-details-section').classList.add('hidden');
  } else {
    await refreshDashboard();
  }
  // Keep activity log visible
}

// Change Context Button
$('#change-context').addEventListener('click', () => {
  $('.tab-link[data-tab="search"]').click();
});

// Auto-refresh every 30s when on dashboard
let dashInterval;
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && !$('#dashboard').classList.contains('hidden')) {
    refreshDashboard();
    dashInterval = setInterval(refreshDashboard, 30000);
  } else {
    clearInterval(dashInterval);
  }
});

loadDashboard();

/* ==================== ADMIN CONSOLE ==================== */
function setupAdminConsole(){
  const createForm = document.getElementById('admin-create-user');
  const usersList = document.getElementById('users-list');
  const userMsg = document.getElementById('admin-user-msg');
  const refreshBtn = document.getElementById('refresh-users');
  const assignForm = document.getElementById('assign-company-form');
  const removeForm = document.getElementById('remove-company-form');
  const deleteForm = document.getElementById('delete-user-form');
  const assignMsg = document.getElementById('assign-msg');
  const removeMsg = document.getElementById('remove-msg');
  const deleteMsg = document.getElementById('delete-msg');

  async function refreshUsers(){
    usersList.innerHTML = '<p class="text-xs text-gray-500">Loading...</p>';
    try {
      const res = await authFetch(`${API_BASE}/auth/admin/users`);
      const data = await res.json();
      if(!res.ok) throw new Error(data.detail || 'Failed');
      if(!data.users.length){
        usersList.innerHTML = '<p class="text-xs text-gray-500">No users</p>';
        return;
      }
      usersList.innerHTML = '';
      data.users.forEach(u => {
        const div = document.createElement('div');
        div.className = 'p-2 border rounded flex justify-between items-center';
        div.innerHTML = `
          <div>
            <p class="font-medium text-xs">${u.email} <span class="ml-1 px-1.5 py-0.5 rounded bg-gray-200 text-[10px] uppercase">${u.role}</span></p>
            <p class="text-[10px] text-gray-500">Companies: ${(u.allowed_companies||[]).join(', ') || '—'}</p>
          </div>
        `;
        usersList.appendChild(div);
      });
    } catch(err){
      usersList.innerHTML = `<p class='text-xs text-red-600'>${err.message}</p>`;
    }
  }

  createForm?.addEventListener('submit', async e => {
    e.preventDefault();
    userMsg.textContent = 'Creating...';
    const fd = new FormData(createForm);
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
      userMsg.textContent = 'User created';
      createForm.reset();
      refreshUsers();
    } catch(err){ userMsg.textContent = err.message; }
  });

  assignForm?.addEventListener('submit', async e => {
    e.preventDefault();
    assignMsg.textContent = 'Assigning...';
    const fd = new FormData(assignForm);
    const payload = { email: fd.get('email'), company: fd.get('company') };
    try {
      const res = await authFetch(`${API_BASE}/auth/admin/assign-company`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
      });
      const data = await res.json();
      if(!res.ok) throw new Error(data.detail || 'Failed');
      assignMsg.textContent = 'Assigned';
      refreshUsers();
    } catch(err){ assignMsg.textContent = err.message; }
  });

  removeForm?.addEventListener('submit', async e => {
    e.preventDefault();
    removeMsg.textContent = 'Removing...';
    const fd = new FormData(removeForm);
    const payload = { email: fd.get('email'), company: fd.get('company') };
    try {
      const res = await authFetch(`${API_BASE}/auth/admin/remove-company`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
      });
      const data = await res.json();
      if(!res.ok) throw new Error(data.detail || 'Failed');
      removeMsg.textContent = 'Removed';
      refreshUsers();
    } catch(err){ removeMsg.textContent = err.message; }
  });

  deleteForm?.addEventListener('submit', async e => {
    e.preventDefault();
    deleteMsg.textContent = 'Deleting...';
    const fd = new FormData(deleteForm);
    const email = encodeURIComponent(fd.get('email'));
    try {
      const res = await authFetch(`${API_BASE}/auth/admin/user/${email}`, { method:'DELETE' });
      const data = await res.json();
      if(!res.ok) throw new Error(data.detail || 'Failed');
      deleteMsg.textContent = 'Deleted';
      deleteForm.reset();
      refreshUsers();
    } catch(err){ deleteMsg.textContent = err.message; }
  });

  refreshBtn?.addEventListener('click', e => { e.preventDefault(); refreshUsers(); });
  refreshUsers();
}

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
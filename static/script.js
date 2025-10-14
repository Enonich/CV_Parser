// CV Parser & Scoring System - Frontend JavaScript

const API_BASE_URL = 'http://localhost:8000';

// Global variables
let cvFile = null;
let jdFile = null;
let cvUploaded = false;
let jdUploaded = false;
let existingCVs = [];
let hasExistingCVs = false;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeDragAndDrop();
    initializeFileInputs();
    loadExistingCVs();
});

// Drag and drop functionality
function initializeDragAndDrop() {
    const cvUploadArea = document.getElementById('cvUploadArea');
    const jdUploadArea = document.getElementById('jdUploadArea');

    // CV upload area
    cvUploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        cvUploadArea.classList.add('dragover');
    });

    cvUploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        cvUploadArea.classList.remove('dragover');
    });

    cvUploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        cvUploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleCVFile(files[0]);
        }
    });

    // JD upload area
    jdUploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        jdUploadArea.classList.add('dragover');
    });

    jdUploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        jdUploadArea.classList.remove('dragover');
    });

    jdUploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        jdUploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleJDFile(files[0]);
        }
    });
}

// File input handling
function initializeFileInputs() {
    const cvFileInput = document.getElementById('cvFile');
    const jdFileInput = document.getElementById('jdFile');

    cvFileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            handleCVFile(e.target.files[0]);
        }
    });

    jdFileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            handleJDFile(e.target.files[0]);
        }
    });
}

// Handle CV file selection
function handleCVFile(file) {
    const allowedTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/png', 'image/jpeg', 'image/jpg'];
    
    if (!allowedTypes.includes(file.type)) {
        showNotification('Please select a valid CV file (PDF, DOCX, PNG, JPG, JPEG)', 'error');
        return;
    }

    cvFile = file;
    uploadCV(file);
}

// Handle JD file selection
function handleJDFile(file) {
    const allowedTypes = ['text/plain', 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
    
    if (!allowedTypes.includes(file.type)) {
        showNotification('Please select a valid job description file (TXT, PDF, DOCX)', 'error');
        return;
    }

    jdFile = file;
    uploadJD(file);
}

// Upload CV file
async function uploadCV(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        showUploadStatus('cv', 'info', 'Uploading CV...');
        
        const response = await fetch(`${API_BASE_URL}/upload-cv/`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            if (result.existing) {
                showUploadStatus('cv', 'success', `CV already exists in database: ${file.name} ✅`);
            } else {
                showUploadStatus('cv', 'success', `CV uploaded successfully: ${file.name}`);
            }
            cvUploaded = true;
            checkReadyToSearch();
        } else {
            showUploadStatus('cv', 'error', `Failed to upload CV: ${result.detail || 'Unknown error'}`);
            // Reset CV file variables on error to allow retry
            cvFile = null;
            cvUploaded = false;
            checkReadyToSearch();
        }
    } catch (error) {
        showUploadStatus('cv', 'error', `Error uploading CV: ${error.message}`);
        // Reset CV file variables on error to allow retry
        cvFile = null;
        cvUploaded = false;
        checkReadyToSearch();
    }
}

// Upload JD file
async function uploadJD(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        showUploadStatus('jd', 'info', 'Uploading Job Description...');
        
        const response = await fetch(`${API_BASE_URL}/upload-jd/`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            if (result.existing) {
                showUploadStatus('jd', 'success', `Job Description already exists in database: ${file.name} ✅`);
            } else {
                showUploadStatus('jd', 'success', `Job Description uploaded successfully: ${file.name}`);
            }
            jdUploaded = true;
            checkReadyToSearch();
        } else {
            showUploadStatus('jd', 'error', `Failed to upload JD: ${result.detail || 'Unknown error'}`);
            // Reset JD file variables on error to allow retry
            jdFile = null;
            jdUploaded = false;
            checkReadyToSearch();
        }
    } catch (error) {
        showUploadStatus('jd', 'error', `Error uploading JD: ${error.message}`);
        // Reset JD file variables on error to allow retry
        jdFile = null;
        jdUploaded = false;
        checkReadyToSearch();
    }
}

// Show upload status
function showUploadStatus(type, status, message) {
    const statusElement = document.getElementById(`${type}UploadStatus`);
    statusElement.innerHTML = `<div class="upload-status ${status}"><i class="fas fa-${getStatusIcon(status)} me-2"></i>${message}</div>`;
}

// Get status icon
function getStatusIcon(status) {
    const icons = {
        'success': 'check-circle',
        'error': 'exclamation-circle',
        'info': 'info-circle'
    };
    return icons[status] || 'info-circle';
}

// Load existing CVs from MongoDB
async function loadExistingCVs() {
    try {
        const response = await fetch(`${API_BASE_URL}/existing-cvs/`);
        const result = await response.json();

        if (response.ok && result.cvs && result.cvs.length > 0) {
            existingCVs = result.cvs;
            hasExistingCVs = true;
            displayExistingCVs();
            checkReadyToSearch();
        } else {
            hasExistingCVs = false;
            hideExistingCVs();
        }
    } catch (error) {
        console.error('Error loading existing CVs:', error);
        hasExistingCVs = false;
        hideExistingCVs();
    }
}

// Display existing CVs
function displayExistingCVs() {
    const existingCvsSection = document.getElementById('existingCvsSection');
    const existingCvsList = document.getElementById('existingCvsList');

    if (existingCVs.length === 0) {
        hideExistingCVs();
        return;
    }

    let html = `<div class="row">`;
    existingCVs.forEach((cv, index) => {
        html += `
            <div class="col-md-6 mb-3">
                <div class="card border-success">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <h6 class="card-title mb-1">
                                    <i class="fas fa-user text-success me-2"></i>
                                    ${cv.name || 'Unknown Name'}
                                </h6>
                                <p class="card-text text-muted mb-1">
                                    <i class="fas fa-envelope me-1"></i>${cv.email || 'No email'}
                                </p>
                                <small class="text-muted">
                                    <i class="fas fa-calendar me-1"></i>${cv.upload_date || 'Unknown date'}
                                </small>
                            </div>
                            <div class="text-end">
                                <span class="badge bg-success">Available</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });
    html += `</div>`;
    html += `<div class="alert alert-success mt-3">
        <i class="fas fa-info-circle me-2"></i>
        <strong>${existingCVs.length} CV(s)</strong> are available in the database and ready for scoring.
    </div>`;

    existingCvsList.innerHTML = html;
    existingCvsSection.style.display = 'block';
}

// Hide existing CVs section
function hideExistingCVs() {
    const existingCvsSection = document.getElementById('existingCvsSection');
    existingCvsSection.style.display = 'none';
}

// Reset uploads and clear file selections
function resetUploads() {
    // Reset global variables
    cvFile = null;
    jdFile = null;
    cvUploaded = false;
    jdUploaded = false;
    
    // Clear file inputs
    document.getElementById('cvFile').value = '';
    document.getElementById('jdFile').value = '';
    
    // Clear upload status messages
    document.getElementById('cvUploadStatus').innerHTML = '';
    document.getElementById('jdUploadStatus').innerHTML = '';
    
    // Update search button state
    checkReadyToSearch();
    
    // Show notification
    showNotification('Uploads reset successfully. You can now upload new files.', 'success');
}

// Check if ready to search
function checkReadyToSearch() {
    const searchBtn = document.getElementById('searchBtn');
    if ((cvUploaded || hasExistingCVs) && jdUploaded) {
        searchBtn.disabled = false;
        const cvSource = hasExistingCVs ? 'database' : 'uploaded';
        searchBtn.innerHTML = `<i class="fas fa-search me-2"></i>Search & Score CVs (${cvSource})`;
    } else if (jdUploaded && !cvUploaded && !hasExistingCVs) {
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<i class="fas fa-lock me-2"></i>Upload CV or use existing CVs';
    } else if ((cvUploaded || hasExistingCVs) && !jdUploaded) {
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<i class="fas fa-lock me-2"></i>Upload Job Description first';
    } else {
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<i class="fas fa-lock me-2"></i>Upload CV and JD first';
    }
}

// Search and score CVs
async function searchCVs() {
    if ((!cvUploaded && !hasExistingCVs) || !jdUploaded) {
        showNotification('Please upload a Job Description and either upload a CV or use existing CVs from the database', 'error');
        return;
    }

    const topKCvs = document.getElementById('topKCvs').value;
    const showDetails = document.getElementById('showDetails').checked;

    const requestBody = {
        top_k_cvs: parseInt(topKCvs),
        show_details: showDetails
    };

    try {
        showLoading(true);
        hideResults();

        const response = await fetch(`${API_BASE_URL}/search-cvs/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        const result = await response.json();

        if (response.ok) {
            displayResults(result.results);
            const cvSource = hasExistingCVs ? 'from database' : 'from uploads';
            showNotification(`Found ${result.results.length} CVs matching your criteria ${cvSource}`, 'success');
        } else {
            showNotification(`Search failed: ${result.detail || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showNotification(`Error searching CVs: ${error.message}`, 'error');
    } finally {
        showLoading(false);
    }
}

// Display search results
function displayResults(results) {
    const resultsSection = document.getElementById('resultsSection');
    const resultsContent = document.getElementById('resultsContent');

    if (!results || results.length === 0) {
        resultsContent.innerHTML = '<div class="alert alert-info"><i class="fas fa-info-circle me-2"></i>No CVs found matching your criteria.</div>';
        resultsSection.style.display = 'block';
        return;
    }

    let html = '';
    results.forEach((result, index) => {
        const scoreClass = getScoreClass(result.total_score);
        const scoreText = getScoreText(result.total_score);
        
        html += `
            <div class="cv-result-card card mb-3 results-animate" style="animation-delay: ${index * 0.1}s">
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-8">
                            <h5 class="card-title">
                                <i class="fas fa-user me-2"></i>CV #${index + 1}
                                <small class="text-muted">(${result.original_identifier || result.cv_id.substring(0, 16) + '...'})</small>
                            </h5>
                            <div class="section-scores mt-3">
                                <h6>Section Scores:</h6>
                                ${generateSectionScores(result.section_scores)}
                            </div>
                        </div>
                        <div class="col-md-4 text-end">
                            <div class="score-badge ${scoreClass}">
                                <strong>${(result.total_score * 100).toFixed(1)}%</strong>
                                <br><small>${scoreText}</small>
                            </div>
                        </div>
                    </div>
                    ${result.section_details && Object.keys(result.section_details).length > 0 ? generateDetailedResults(result.section_details) : ''}
                </div>
            </div>
        `;
    });

    resultsContent.innerHTML = html;
    resultsSection.style.display = 'block';
}

// Generate section scores HTML
function generateSectionScores(sectionScores) {
    let html = '';
    for (const [section, score] of Object.entries(sectionScores)) {
        const percentage = (score * 100).toFixed(1);
        html += `
            <div class="section-score">
                <div class="d-flex justify-content-between">
                    <span class="section-name">${formatSectionName(section)}</span>
                    <span class="section-percentage">${percentage}%</span>
                </div>
                <div class="section-score-bar">
                    <div class="section-score-fill" style="width: ${percentage}%"></div>
                </div>
            </div>
        `;
    }
    return html;
}

// Generate detailed results HTML
function generateDetailedResults(sectionDetails) {
    let html = '<div class="mt-3"><h6>Detailed Matching:</h6>';
    
    for (const [section, matches] of Object.entries(sectionDetails)) {
        if (matches && matches.length > 0) {
            html += `<div class="mt-2"><strong>${formatSectionName(section)}:</strong>`;
            matches.forEach(match => {
                html += `
                    <div class="detail-item">
                        <small>
                            <strong>CV Section:</strong> ${match.cv_section || 'N/A'} | 
                            <strong>Similarity:</strong> ${(match.similarity * 100).toFixed(1)}%
                        </small>
                    </div>
                `;
            });
            html += '</div>';
        }
    }
    
    html += '</div>';
    return html;
}

// Format section name
function formatSectionName(section) {
    return section.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

// Get score class
function getScoreClass(score) {
    if (score >= 0.8) return 'score-excellent';
    if (score >= 0.6) return 'score-good';
    if (score >= 0.4) return 'score-fair';
    return 'score-poor';
}

// Get score text
function getScoreText(score) {
    if (score >= 0.8) return 'Excellent Match';
    if (score >= 0.6) return 'Good Match';
    if (score >= 0.4) return 'Fair Match';
    return 'Poor Match';
}

// Show/hide loading spinner
function showLoading(show) {
    const loadingSpinner = document.getElementById('loadingSpinner');
    const searchBtn = document.getElementById('searchBtn');
    
    if (show) {
        loadingSpinner.style.display = 'block';
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
    } else {
        loadingSpinner.style.display = 'none';
        checkReadyToSearch();
    }
}

// Hide results
function hideResults() {
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.style.display = 'none';
}

// Show notification
function showNotification(message, type = 'info') {
    const toast = document.getElementById('notificationToast');
    const toastMessage = document.getElementById('toastMessage');
    
    // Update toast styling based on type
    toast.className = `toast bg-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} text-white`;
    
    toastMessage.textContent = message;
    
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
}

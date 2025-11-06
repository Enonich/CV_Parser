# Admin Panel Features

## Overview
The admin panel provides comprehensive system management capabilities for the CV Parser Pro application. Admins have full access to all companies, can manage users, perform bulk operations, maintain system health, and monitor activity.

## Feature Summary

| Feature | Purpose | Status |
|---------|---------|--------|
| User Management | Add/edit/delete recruiters | ✅ Implemented |
| Company & Job Browser | View all tenants and their data | ✅ Implemented |
| CV/JD Bulk Delete | Clean up old data | ✅ Implemented |
| Embedding Reindex | Fix broken vectors | ✅ Implemented |
| System Health Check | Monitor system status | ✅ Implemented |
| Data Export | Backup company data | ✅ Implemented |
| Activity Logs | View errors, uploads, searches | ✅ Implemented |

---

## 1. User Management

**Location:** Admin Dashboard → Users Tab

### Capabilities:
- **Create New Users**
  - Set email, password, role (admin/user)
  - Assign companies on creation
  - Minimum 8 character password requirement

- **Manage Company Access**
  - Assign companies to existing users
  - Remove company access from users
  - Users can access multiple companies

- **Delete Users**
  - Permanent user deletion
  - Removes user from authentication system

### API Endpoints:
- `POST /auth/admin/create-user` - Create new user
- `POST /auth/admin/assign-company` - Assign company to user
- `POST /auth/admin/remove-company` - Remove company from user
- `DELETE /auth/admin/user/{email}` - Delete user
- `GET /auth/admin/users` - List all users

---

## 2. Company & Job Data Browser

**Location:** Admin Dashboard → Data Browser Tab

### Features:
- **Hierarchical Company View**
  - Lists all companies in the system
  - Shows jobs under each company
  - Displays CV count per job
  - Real-time statistics

- **Statistics Dashboard**
  - Total companies count
  - Total jobs across all companies
  - Total CVs in system
  - Auto-refreshes on demand

### API Endpoints:
- `GET /companies/` - List all companies
- `GET /jobs/?company_name={company}` - List jobs for company
- `GET /existing-cvs/?company_name={company}&job_title={job}` - Get CV count

---

## 3. Bulk Delete Operations

**Location:** Admin Dashboard → Bulk Ops Tab

### Delete CVs
- Select company and job
- Deletes all CVs for that specific job
- Removes both MongoDB documents and ChromaDB embeddings
- Confirmation checkbox required
- Irreversible operation with double-confirmation

### Delete JDs
- Select company
- Optional: Select specific job (or delete all JDs for company)
- Removes JD documents and embeddings
- Confirmation required

### Delete Entire Company
- **NUCLEAR OPTION** - Deletes everything for a company
- Must type exact company name to confirm
- Deletes:
  - Entire MongoDB database for company
  - All ChromaDB embeddings (CVs and JDs)
  - All associated job data
- Triple confirmation required
- Permanent and irreversible

### API Endpoints:
- `POST /admin/bulk-delete-cvs` - Delete CVs for a job
- `POST /admin/bulk-delete-jds` - Delete JDs (specific or all)
- `DELETE /admin/delete-company/{company_name}` - Delete entire company

**Security:** All endpoints require admin role authentication

---

## 4. System Maintenance

**Location:** Admin Dashboard → Maintenance Tab

### Reindex Embeddings
- **Purpose:** Rebuild vector embeddings for corrupted or outdated data
- **Options:**
  - Reindex CVs only
  - Reindex JDs only
  - Reindex both CVs and JDs
- **Process:**
  - Fetches documents from MongoDB
  - Regenerates embeddings using current model
  - Updates ChromaDB collections
  - Reports number of items reindexed

### Database Health Check
- **Checks:**
  - MongoDB connectivity and status
  - ChromaDB directory accessibility
  - Disk space availability
  - System resource health
- **Output:**
  - Overall system status (Healthy/Degraded)
  - Individual check results with details
  - Color-coded status indicators

### Data Export
- **Formats:** JSON or CSV
- **Content:**
  - All MongoDB collections for selected company
  - Includes CVs, JDs, and metadata
  - ObjectIDs converted to strings for portability
- **Use Cases:**
  - Backup before major changes
  - Migration to different systems
  - Audit and compliance

### API Endpoints:
- `POST /admin/reindex` - Rebuild embeddings
- `GET /admin/health-check` - System health status
- `GET /admin/export/{company_name}?format={json|csv}` - Export data

---

## 5. Activity Logs & Monitoring

**Location:** Admin Dashboard → Logs Tab

### Log Viewer
- **Filters:**
  - Action type (Upload CV, Upload JD, Search, Delete, Error)
  - Company name
  - Time range (Last hour, 24 hours, 7 days, 30 days)
- **Display:**
  - Timestamp of each action
  - Action type with color coding
  - Detailed message
  - User who performed action
  - Associated company

### Statistics
- **Real-time Metrics:**
  - Total uploads (CVs + JDs)
  - Total searches performed
  - Active users count
  - Error count
- **Visual Indicators:**
  - Color-coded KPI cards
  - Automatic updates on refresh

### Export Logs
- Download complete logs as CSV
- Includes all fields for analysis
- Useful for auditing and compliance

### API Endpoints:
- `GET /admin/logs?action_type={type}&company={name}&hours={n}` - Fetch logs
- `GET /admin/logs/export` - Export logs as CSV

---

## Access Control

### Admin-Only Features
All admin features require:
1. **Authentication:** Valid JWT token
2. **Authorization:** User role must be "admin"
3. **Verification:** Backend checks role on every request

### Non-Admin Access
- Regular users redirected to user dashboard
- Cannot access admin HTML page
- API returns 403 Forbidden for admin endpoints

---

## Navigation

### Admin Dashboard Tabs:
1. **Dashboard** - Overview with KPIs and top candidates
2. **Upload CV** - Add new candidate CVs
3. **Upload JD** - Add job descriptions
4. **Search CVs** - Search and rank candidates
5. **Users** - User management (admin only)
6. **Data Browser** - Browse all company data (admin only)
7. **Bulk Ops** - Mass deletion operations (admin only)
8. **Maintenance** - System health and reindexing (admin only)
9. **Logs** - Activity monitoring (admin only)

### Visual Design
- Color-coded tabs for easy navigation
- Active tab highlighting
- Icon-based identification
- Responsive layout for all screen sizes

---

## Safety Features

### Confirmation Requirements
- **Single Confirmation:** User creation, company assignment
- **Double Confirmation:** Bulk CV/JD deletion
- **Triple Confirmation:** Company deletion (checkbox + name typing + alert)

### Audit Trail
- All admin actions logged
- Timestamps and user attribution
- Export capability for compliance

### Irreversible Warnings
- Prominent warning badges on destructive operations
- Color-coded danger zones (red for critical actions)
- Clear explanations of consequences

---

## Usage Tips

1. **Regular Health Checks:** Run weekly to catch issues early
2. **Backup Before Bulk Delete:** Always export data before mass deletions
3. **Monitor Logs Daily:** Check for errors and unusual activity
4. **Reindex After Model Updates:** If you change embedding models, reindex all data
5. **User Access Reviews:** Periodically review user permissions and company access

---

## Future Enhancements

Potential additions:
- Real-time database logging (currently mock data)
- Scheduled backups
- Email notifications for errors
- Advanced analytics dashboard
- Bulk user import/export
- API rate limiting controls
- System performance metrics

---

## Technical Notes

### Backend Stack:
- FastAPI with role-based access control
- MongoDB for document storage
- ChromaDB for vector embeddings
- JWT authentication

### Frontend Stack:
- Vanilla JavaScript with Fetch API
- Tailwind CSS for styling
- Font Awesome icons
- No framework dependencies

### File Locations:
- Admin HTML: `static/admin.html`
- Admin JS: `static/admin.js`
- Backend APIs: `workflow.py` (admin endpoints section)
- Auth APIs: `auth.py`

---

## Security Considerations

1. **Always use HTTPS** in production
2. **Rotate JWT secrets** regularly
3. **Use strong passwords** for admin accounts
4. **Enable 2FA** (future enhancement)
5. **Regular security audits** of user permissions
6. **Monitor admin activity** through logs
7. **Limit admin accounts** to necessary personnel only

---

**Document Version:** 1.0  
**Last Updated:** October 29, 2025  
**Author:** CV Parser Pro Development Team

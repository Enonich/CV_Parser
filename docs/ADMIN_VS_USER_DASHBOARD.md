# Admin vs User Dashboard Implementation

## Overview
The system now differentiates between admin and regular user experiences, providing tailored dashboards based on user roles.

## 🔑 Key Changes

### **Regular User Experience**

#### Dashboard
- **Auto-loaded Company Context**: User's company is automatically displayed (no selection needed)
- **Job Title Selector**: Dropdown to select from available job titles within their company
- **Company Stats**: View CVs count, top matches, and rankings for selected job
- **No Company Switching**: The "Change Context" button is hidden for regular users

#### Upload CV/JD
- **Pre-filled Company**: Company field is auto-filled with user's company and read-only
- **Only Job Title Input**: Users only need to enter the job title
- **Automatic Refresh**: Job list refreshes after uploading CV/JD

#### Search & Rank
- **Company Pre-selected**: Search company dropdown shows only user's company (disabled)
- **Job Selection**: Users can select from their company's job titles
- **Historical Rankings**: View past CV rankings and scores for each job

### **Admin Experience**

#### Dashboard
- **Full Control**: Can select any company and job title
- **Change Context**: Can switch between companies freely
- **System Overview**: View stats across all companies

#### Upload CV/JD
- **Manual Company Entry**: Must enter company name manually
- **Full Flexibility**: Can upload for any company/job combination

#### Search & Rank
- **All Companies**: Access to search across all companies in system
- **User Management**: Admin tab for creating users, assigning companies

#### Admin Console
- **User Management**: Create, delete users
- **Company Assignment**: Assign/remove company access for users
- **Role Management**: Set user roles (admin/user)

## 🎯 User Flow

### Regular User Login:
1. User logs in with email/password + company name
2. Dashboard loads automatically showing their company
3. User selects a job title from dropdown
4. Dashboard shows CV rankings and stats for that job
5. User can upload more CVs/JDs (company auto-filled)
6. User can search CVs within their job titles

### Admin Login:
1. Admin logs in with admin email/password
2. Full dashboard with company selector
3. Can view any company's data
4. Access to Admin tab for user/company management
5. Can upload CVs/JDs for any company

## 📋 Database Structure

### User Document (MongoDB - Auth.users):
```json
{
  "email": "user@company.com",
  "password_hash": "...",
  "role": "user",  // or "admin"
  "allowed_companies": ["CompanyName"],
  "created_at": "2025-10-29T...",
  "last_login": "2025-10-29T..."
}
```

## 🔧 Technical Implementation

### Frontend Changes (`app.js`):
- Added `userRole`, `userCompany`, `allowedCompanies` global variables
- New functions: `setupUserDashboard()`, `setupAdminDashboard()`, `loadUserJobs()`
- Modified `loadCompanies()` to check user role
- Updated CV/JD upload handlers to auto-fill company for users
- Company input fields are readonly for regular users

### Backend Support (`auth.py`):
- Already supports company assignment via `allowed_companies` array
- Admin seeding from `.env` file
- JWT tokens include role and allowed_companies

## 🚀 Benefits

1. **Simplified UX for Users**: No need to select company repeatedly
2. **Data Isolation**: Users only see their company's data
3. **Reduced Errors**: Auto-filled fields prevent typos
4. **Historical Tracking**: Easy to view past rankings by job title
5. **Admin Flexibility**: Admins retain full system control

## 📝 Next Steps

1. **Job History View**: Add a dedicated view to show ranking history over time
2. **Analytics Dashboard**: Charts showing trends in candidate quality
3. **Notifications**: Alert users when new high-scoring CVs are added
4. **Export Functionality**: Download candidate reports by job title
5. **Batch Operations**: Upload multiple CVs at once

## 🔐 Security Notes

- Users can only access their assigned companies
- API endpoints validate user permissions via JWT
- Admin functions require `role: "admin"` in token
- Company data is isolated by database naming convention

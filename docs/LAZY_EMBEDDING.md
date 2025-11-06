# Lazy Embedding Implementation

## Overview
Changed the workflow to delay embedding until search time, ensuring both CVs and JD exist before allowing search.

## Changes Made

### 1. **CV Upload** (`backend/api/workflow.py`)
- **Before**: Automatically embedded CVs immediately after upload
- **After**: Only stores CV data in MongoDB, no embedding
- CVs are now embedded on-demand when search is triggered

### 2. **JD Upload** (`backend/api/workflow.py`)
- **Before**: Automatically embedded JD immediately after upload
- **After**: Only stores JD data in MongoDB, no embedding
- JD is now embedded on-demand when search is triggered

### 3. **New Endpoint** - `/data-status/` 
- **Purpose**: Check if both CVs and JD exist for a given company/job
- **Returns**:
  ```json
  {
    "cv_count": 5,
    "jd_exists": true,
    "can_search": true,
    "company_name": "company_name",
    "job_title": "job_title"
  }
  ```

### 4. **Search Endpoint Enhancement** (`/search-cvs/`)
- **New Behavior**:
  1. Checks if JD exists → if not, returns 404
  2. Checks if CVs exist → if not, returns 404
  3. Embeds JD if not already embedded
  4. Embeds all CVs if not already embedded
  5. Proceeds with vector search
  6. Applies reranking
  7. Returns results

### 5. **Frontend Changes** (`static/app.js`)
- **Search Button**: Disabled by default
- **Job Selection Handler**: 
  - Calls `/data-status/` when job is selected
  - Enables/disables search button based on data availability
  - Shows helpful tooltip messages:
    - "Please upload CVs and Job Description first"
    - "Please upload Job Description first"
    - "Please upload CVs first"
    - "Search X CVs" (when ready)
- **Search Process**: Shows "Embedding & Searching..." during search

### 6. **JD Embedder Enhancement** (`backend/embedders/jd_embedder.py`)
- **New Method**: `embed_job_description_from_json(json_file_path)`
- **Purpose**: Embed JD from already-extracted JSON (from MongoDB)
- **Use Case**: On-demand embedding during search

## Workflow

### Old Workflow
```
1. Upload CV → Extract → Store in MongoDB → Embed immediately
2. Upload JD → Extract → Store in MongoDB → Embed immediately  
3. Search → Use existing embeddings → Return results
```

### New Workflow
```
1. Upload CV → Extract → Store in MongoDB (NO embedding)
2. Upload JD → Extract → Store in MongoDB (NO embedding)
3. Select Job → Check if CVs & JD exist → Enable/Disable search button
4. Click Search:
   a. Check if JD exists (error if not)
   b. Check if CVs exist (error if not)
   c. Embed JD if not already embedded
   d. Embed all CVs if not already embedded
   e. Perform vector search
   f. Apply reranking
   g. Return results
```

## Benefits

✅ **Faster Uploads**: CV and JD uploads complete instantly  
✅ **Resource Efficient**: Only embed when actually needed  
✅ **Better UX**: User knows if they can search (button disabled/enabled)  
✅ **Clear Feedback**: Helpful messages guide user to upload missing data  
✅ **Consistent State**: All embeddings happen together at search time  
✅ **No Wasted Embeddings**: Don't embed CVs/JDs that may never be searched  

## User Experience

### Before Search
- User uploads CVs → "CV uploaded successfully"
- User uploads JD → "JD uploaded successfully"
- User selects job → Button automatically enables/disables
- Button tooltip shows what's missing (if anything)

### During Search
- Button shows "Embedding & Searching..."
- First search may take longer (embedding happens)
- Subsequent searches are fast (embeddings cached)

### Error Messages
- "No job description found for {job}. Please upload a JD first."
- "No CVs found for {job}. Please upload CVs first."
- Clear actionable feedback

## Technical Details

### Embedding Caching
- ChromaDB persists embeddings to disk
- On subsequent searches, checks if embeddings exist
- Only re-embeds if collection is empty
- Smart detection: counts documents in vector store

### Performance
- **First search**: Slow (embedding + search)
- **Subsequent searches**: Fast (only search)
- **Upload time**: Very fast (no embedding)

## Testing

1. **Upload CV without JD**: Search button disabled, tooltip says "upload JD"
2. **Upload JD without CVs**: Search button disabled, tooltip says "upload CVs"  
3. **Upload both**: Search button enabled, tooltip shows CV count
4. **First search**: Takes time (embedding), succeeds
5. **Second search**: Fast (uses cached embeddings)

---

**Date Implemented:** October 31, 2025  
**Status:** ✅ Complete and Tested

# Survey System Documentation

This directory contains all documentation related to the site survey workflow for pre-installation assessment.

## 📋 Contents

| Document | Description |
|----------|-------------|
| [SURVEY_VALIDATION_SUMMARY.md](./SURVEY_VALIDATION_SUMMARY.md) | Survey validation logic and rules |
| [SURVEY_REJECTION_WORKFLOW_SPECS.md](./SURVEY_REJECTION_WORKFLOW_SPECS.md) | Rejection workflow specifications |
| [SURVEY_APPROVAL_FIX.md](./SURVEY_APPROVAL_FIX.md) | Approval process fixes and improvements |
| [SITE_SURVEY_IMPROVEMENTS.md](./SITE_SURVEY_IMPROVEMENTS.md) | Survey system enhancements |
| [CONDUCT_SURVEY_IMPLEMENTATION.md](./CONDUCT_SURVEY_IMPLEMENTATION.md) | Survey conduct implementation |

## 🔄 Survey Workflow

```
Survey Request Submitted
    ↓
Technician Assigned
    ↓
Survey Conducted (Photos, GPS, Notes)
    ↓
Survey Submitted for Review
    ↓
┌──────────────┴──────────────┐
│                              │
Approved                   Rejected
│                              │
Installation Proceeds      Resubmission Required
```

## 🎯 Key Features

- **Survey Request** - Customer/admin survey request
- **Technician Assignment** - Auto/manual assignment
- **Survey Conduct** - Photo upload, GPS coordinates, notes
- **Approval/Rejection** - Manager review workflow
- **Resubmission** - Rejection with reasons and resubmit
- **Validation** - Data validation and quality checks

## 🚀 Quick Start

### For Developers

1. Review [CONDUCT_SURVEY_IMPLEMENTATION.md](./CONDUCT_SURVEY_IMPLEMENTATION.md) for implementation
2. Check [SURVEY_VALIDATION_SUMMARY.md](./SURVEY_VALIDATION_SUMMARY.md) for validation rules
3. See [SURVEY_REJECTION_WORKFLOW_SPECS.md](./SURVEY_REJECTION_WORKFLOW_SPECS.md) for rejection handling

### For Technicians

1. Mobile app guides available in main documentation
2. Survey conduct requirements in [CONDUCT_SURVEY_IMPLEMENTATION.md](./CONDUCT_SURVEY_IMPLEMENTATION.md)
3. Photo and GPS requirements specified

### For Managers

1. Review [SURVEY_APPROVAL_FIX.md](./SURVEY_APPROVAL_FIX.md) for approval process
2. Check [SURVEY_REJECTION_WORKFLOW_SPECS.md](./SURVEY_REJECTION_WORKFLOW_SPECS.md) for rejection workflow
3. Quality control guidelines in validation summary

## 📋 Survey Requirements

### Required Information

- ✅ **GPS Coordinates** - Exact installation location
- ✅ **Photos** - Minimum 3 photos (site, equipment area, access)
- ✅ **Notes** - Site conditions, obstacles, recommendations
- ✅ **Technician Details** - Who conducted the survey
- ✅ **Date & Time** - When survey was conducted

### Validation Rules

- GPS coordinates must be valid
- Photos must be clear and relevant
- Notes must describe site conditions
- Survey must be within service area

## 📊 Survey Status Codes

| Status | Description |
|--------|-------------|
| `pending` | Survey requested, awaiting assignment |
| `assigned` | Technician assigned |
| `in_progress` | Survey being conducted |
| `submitted` | Submitted for review |
| `approved` | Approved, ready for installation |
| `rejected` | Rejected, needs resubmission |
| `resubmitted` | Resubmitted after rejection |

## 🔗 Related Documentation

- **Installations**: [../installations/](../installations/) - Installation workflow
- **Features**: [../features/](../features/) - UI improvements

---

**Back to**: [Documentation Index](../INDEX.md)

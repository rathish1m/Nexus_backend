def kyc_status_context(request):
    """
    Context processor to make KYC status available on all pages
    """
    if not request.user.is_authenticated:
        return {"kyc_status": "not_authenticated"}

    try:
        user = request.user
        # Default KYC status
        kyc_status = "Not submitted"
        kyc_rejection_reason = ""
        kyc_rejection_details = ""

        # Check for existing KYC records (prefer rejected with details)
        personal_kyc = getattr(user, "personnal_kyc", None)
        company_kyc = getattr(user, "company_kyc", None)

        # Prefer the KYC that is rejected and has details
        if (
            personal_kyc
            and personal_kyc.status == "rejected"
            and (personal_kyc.remarks or personal_kyc.get_rejection_reason_display())
        ):
            kyc_status = personal_kyc.status
            kyc_rejection_reason = personal_kyc.get_rejection_reason_display()
            kyc_rejection_details = personal_kyc.remarks or ""
        elif (
            company_kyc
            and company_kyc.status == "rejected"
            and (company_kyc.remarks or company_kyc.get_rejection_reason_display())
        ):
            kyc_status = company_kyc.status
            kyc_rejection_reason = company_kyc.get_rejection_reason_display()
            kyc_rejection_details = company_kyc.remarks or ""
        elif personal_kyc:
            kyc_status = personal_kyc.status
        elif company_kyc:
            kyc_status = company_kyc.status

        return {
            "kyc_status": kyc_status,
            "kyc_rejection_reason": kyc_rejection_reason,
            "kyc_rejection_details": kyc_rejection_details,
        }
    except Exception:
        # Return safe defaults if there's any error
        return {
            "kyc_status": "Not submitted",
            "kyc_rejection_reason": "",
            "kyc_rejection_details": "",
        }

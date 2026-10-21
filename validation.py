
REQUIRED_DOCUMENTS = {
    "personal_loan": {
        "pan",
        "identity_proof",
        "address_proof",
        "bank_statement",
        "income_proof",
    }
}


def validate_documents(loan_product, documents):
    issues = []
    required = REQUIRED_DOCUMENTS.get(loan_product)

    if required is None:
        return [{
            "code": "UNSUPPORTED_LOAN_PRODUCT",
            "message": "Loan product is not configured."
        }]

    uploaded = {
        doc.document_type.strip().lower()
        for doc in documents
    }

    for missing in sorted(required - uploaded):
        issues.append({
            "code": "MISSING_DOCUMENT",
            "document_type": missing,
            "message": f"Please upload {missing}."
        })

    for doc in documents:
        fields = doc.extracted_fields or {}

        if fields.get("expired") is True:
            issues.append({
                "code": "EXPIRED_DOCUMENT",
                "document_type": doc.document_type,
                "message": "Please provide an acceptable valid document."
            })

        confidence = fields.get("extraction_confidence")
        if (
            isinstance(confidence, (int, float))
            and confidence < 0.80
        ):
            issues.append({
                "code": "LOW_EXTRACTION_CONFIDENCE",
                "document_type": doc.document_type,
                "message": "Please upload a clearer document."
            })

    return issues

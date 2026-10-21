
import os
import uuid
from pathlib import Path

import streamlit as st
from sqlalchemy import select

from database import (
    SessionLocal,
    LoanApplication,
    LoanDocument,
    ManagerReview,
    init_db,
)
from validation import validate_documents


# ---------- Configuration ----------

st.set_page_config(
    page_title="Bank Loan Verification Agent",
    page_icon="🏦",
    layout="wide",
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file

init_db()


# ---------- Database helpers ----------

def get_application(db, application_id):
    return db.get(LoanApplication, application_id)


def get_documents(db, application_id):
    return db.scalars(
        select(LoanDocument).where(
            LoanDocument.application_id == application_id
        )
    ).all()


def save_uploaded_file(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Upload a PDF, PNG, or JPEG file.")

    content = uploaded_file.getvalue()

    if not content or len(content) > MAX_FILE_SIZE:
        raise ValueError("File is empty or exceeds the 10 MB limit.")

    # Never use the uploaded filename as a filesystem path.
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = UPLOAD_DIR / stored_name
    destination.write_bytes(content)

    return str(destination)


def create_documents(db, application_id, files):
    for document_type, uploaded_file in files:
        if uploaded_file is None:
            continue

        file_reference = save_uploaded_file(uploaded_file)

        db.add(LoanDocument(
            application_id=application_id,
            document_type=document_type,
            file_reference=file_reference,
            extracted_fields={},
        ))


def verify_and_update(db, application):
    documents = get_documents(db, application.id)

    issues = validate_documents(
        application.loan_product,
        documents,
    )

    application.issues = issues
    application.status = (
        "needs_correction" if issues else "pending_manager"
    )
    db.commit()

    return issues


# ---------- Applicant portal ----------

def applicant_portal():
    st.header("Applicant Portal")
    st.write("Submit your loan application and supporting documents.")

    with st.form("new_application"):
        applicant_id = st.text_input(
            "Applicant reference ID",
            placeholder="DEMO-001",
        )

        loan_product = st.selectbox(
            "Loan product",
            ["personal_loan"],
        )

        st.subheader("Upload supporting documents")

        document_types = [
            ("PAN", "pan"),
            ("Identity proof", "identity_proof"),
            ("Address proof", "address_proof"),
            ("Bank statement", "bank_statement"),
            ("Income proof", "income_proof"),
        ]

        uploaded_files = []
        for label, document_type in document_types:
            file = st.file_uploader(
                label,
                type=["pdf", "png", "jpg", "jpeg"],
                key=f"new_{document_type}",
            )
            uploaded_files.append((document_type, file))

        submitted = st.form_submit_button(
            "Submit application",
            type="primary",
        )

    if submitted:
        if not applicant_id.strip():
            st.error("Enter an applicant reference ID.")
            return

        if not any(file for _, file in uploaded_files):
            st.error("Upload at least one supporting document.")
            return

        try:
            with SessionLocal() as db:
                application = LoanApplication(
                    applicant_id=applicant_id.strip(),
                    loan_product=loan_product,
                    status="uploaded",
                )
                db.add(application)
                db.flush()

                create_documents(
                    db, application.id, uploaded_files
                )

                db.commit()
                application_id = application.id

            st.success(
                f"Application submitted: {application_id}"
            )
            st.info(
                "Save this application ID to check its status."
            )
        except Exception as exc:
            st.error(f"Submission failed: {exc}")


# ---------- Verification and corrections ----------

def verification_portal():
    st.header("Application Verification")

    application_id = st.text_input(
        "Application ID",
        key="verification_application_id",
    )

    if not application_id:
        return

    with SessionLocal() as db:
        application = get_application(db, application_id)

        if not application:
            st.warning("Application not found.")
            return

        st.write("**Current status:**", application.status)
        st.write("**Loan product:**", application.loan_product)

        documents = get_documents(db, application.id)

        st.write("**Uploaded document types**")
        st.write(
            [doc.document_type for doc in documents]
        )

        if application.status in {
            "uploaded", "needs_correction"
        }:
            if st.button("Verify documents", type="primary"):
                issues = verify_and_update(db, application)

                if issues:
                    st.warning("Corrections are required.")
                    for issue in issues:
                        st.write(
                            f"- {issue['message']}"
                        )
                else:
                    st.success(
                        "Checks passed. Sent to manager review."
                    )

                st.rerun()

        if application.status == "needs_correction":
            st.subheader("Upload corrected documents")

            with st.form("correction_form"):
                document_types = [
                    ("PAN", "pan"),
                    ("Identity proof", "identity_proof"),
                    ("Address proof", "address_proof"),
                    ("Bank statement", "bank_statement"),
                    ("Income proof", "income_proof"),
                ]

                corrected_files = []
                for label, document_type in document_types:
                    file = st.file_uploader(
                        label,
                        type=["pdf", "png", "jpg", "jpeg"],
                        key=f"correction_{document_type}",
                    )
                    corrected_files.append((document_type, file))

                resubmit = st.form_submit_button(
                    "Resubmit documents"
                )

            if resubmit:
                try:
                    # Learning version: replace the document set.
                    # Production should preserve every document version.
                    with SessionLocal() as write_db:
                        current = get_application(
                            write_db, application_id
                        )

                        if (
                            not current
                            or current.status != "needs_correction"
                        ):
                            st.error(
                                "Application state has changed. Refresh."
                            )
                            return

                        old_documents = get_documents(
                            write_db, application_id
                        )
                        for doc in old_documents:
                            write_db.delete(doc)

                        create_documents(
                            write_db,
                            application_id,
                            corrected_files,
                        )

                        current.status = "uploaded"
                        current.issues = []
                        write_db.commit()

                    st.success(
                        "Documents resubmitted. Run verification again."
                    )
                    st.rerun()

                except Exception as exc:
                    st.error(f"Resubmission failed: {exc}")

        if application.issues:
            st.subheader("Verification findings")
            for issue in application.issues:
                st.write(
                    f"- **{issue['code']}**: {issue['message']}"
                )


# ---------- Manager dashboard ----------

def manager_dashboard():
    st.header("Manager Dashboard")

    with SessionLocal() as db:
        applications = db.scalars(
            select(LoanApplication)
            .where(LoanApplication.status == "pending_manager")
            .order_by(LoanApplication.created_at)
        ).all()

        if not applications:
            st.info("No applications awaiting manager review.")
            return

        application_options = {
            (
                f"{a.id} | Applicant {a.applicant_id} "
                f"| {a.loan_product}"
            ): a.id
            for a in applications
        }

        selected_label = st.selectbox(
            "Select an application",
            list(application_options.keys()),
        )
        application_id = application_options[selected_label]

        application = get_application(db, application_id)
        documents = get_documents(db, application_id)

        st.subheader("Application details")
        st.write("Application ID:", application.id)
        st.write("Applicant reference:", application.applicant_id)
        st.write("Loan product:", application.loan_product)

        st.subheader("Submitted documents")
        for doc in documents:
            st.write(
                f"- {doc.document_type}: "
                f"{doc.file_reference or 'No file reference'}"
            )

        st.subheader("Record manager decision")

        decision = st.radio(
            "Decision",
            ["approve", "reject"],
            horizontal=True,
        )

        reason = st.text_area(
            "Decision rationale",
            placeholder="Enter the review rationale.",
        )

        if st.button("Submit manager decision", type="primary"):
            if len(reason.strip()) < 3:
                st.error("Provide a decision rationale.")
                return

            # DEMO ONLY: this is not authenticated identity.
            manager_id = "demo-manager"

            application.status = (
                "approved" if decision == "approve"
                else "rejected"
            )

            db.add(ManagerReview(
                application_id=application.id,
                manager_id=manager_id,
                decision=decision,
                reason=reason.strip(),
            ))

            db.commit()

            if decision == "approve":
                st.success(
                    "Approved. Final eligibility checks are still required."
                )
            else:
                st.warning(
                    "Rejected. The application is now closed in this demo."
                )

            st.rerun()


# ---------- Navigation ----------

page = st.sidebar.radio(
    "Navigation",
    [
        "Applicant Portal",
        "Verification & Corrections",
        "Manager Dashboard",
    ],
)

if page == "Applicant Portal":
    applicant_portal()
elif page == "Verification & Corrections":
    verification_portal()
else:
    manager_dashboard()

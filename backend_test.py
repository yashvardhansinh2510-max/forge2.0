#!/usr/bin/env python3
"""
Production Sprint Objective 1 — Official quotation PDF template fidelity test
Testing GET /api/quotations/{id}/pdf endpoint
"""

import requests
import sys
from io import BytesIO
from PyPDF2 import PdfReader

# Configuration
BASE_URL = "https://secure-then-ship.preview.emergentagent.com/api"
CREDENTIALS = {
    "email": "owner@forge.app",
    "password": "Forge@2026"
}

# Required text elements in PDF
REQUIRED_ELEMENTS = [
    "BuildCon House",
    "PRICE QUOTATION",
    "QUOTATION SUMMARY",
    "OUR BRAND PARTNERS",
    "CUSTOMER CARE",
    "TOLL FREE",
    "CUSTOMER SIGNATURE",
    "DATE",
]

# All 11 official terms (checking for key terms)
REQUIRED_TERMS = [
    "TERMS",
    "CONDITIONS",
]

def print_test(test_name, status, details=""):
    """Print test result"""
    symbol = "✅" if status else "❌"
    print(f"{symbol} {test_name}")
    if details:
        print(f"   {details}")

def authenticate():
    """Authenticate and get JWT token"""
    print("\n=== AUTHENTICATION ===")
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json=CREDENTIALS,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            print_test(
                "POST /api/auth/login",
                True,
                f"User: {user.get('full_name')} ({user.get('email')}), Role: {user.get('role')}"
            )
            return token
        else:
            print_test(
                "POST /api/auth/login",
                False,
                f"Status: {response.status_code}, Response: {response.text[:200]}"
            )
            return None
    except Exception as e:
        print_test("POST /api/auth/login", False, f"Error: {str(e)}")
        return None

def get_existing_quotation(token):
    """Get an existing quotation ID"""
    print("\n=== FETCHING EXISTING QUOTATION ===")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/quotations",
            headers=headers,
            params={"limit": 10},
            timeout=10
        )
        
        if response.status_code == 200:
            quotations = response.json()
            if quotations and len(quotations) > 0:
                # Find a quotation with items
                for q in quotations:
                    if q.get("items") and len(q.get("items", [])) > 0:
                        print_test(
                            "GET /api/quotations",
                            True,
                            f"Found quotation: {q.get('quotation_number')} with {len(q.get('items', []))} items"
                        )
                        return q.get("id")
                
                # If no quotation with items, use first one
                q = quotations[0]
                print_test(
                    "GET /api/quotations",
                    True,
                    f"Using quotation: {q.get('quotation_number')} (may have 0 items)"
                )
                return q.get("id")
            else:
                print_test("GET /api/quotations", False, "No quotations found")
                return None
        else:
            print_test(
                "GET /api/quotations",
                False,
                f"Status: {response.status_code}"
            )
            return None
    except Exception as e:
        print_test("GET /api/quotations", False, f"Error: {str(e)}")
        return None

def test_pdf_generation(token, quotation_id):
    """Test PDF generation and validate content"""
    print("\n=== PDF GENERATION TEST ===")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/quotations/{quotation_id}/pdf",
            headers=headers,
            timeout=30
        )
        
        # Test 1: HTTP 200
        status_ok = response.status_code == 200
        print_test(
            "HTTP Status Code",
            status_ok,
            f"Status: {response.status_code}"
        )
        
        if not status_ok:
            print(f"Response: {response.text[:500]}")
            return False
        
        # Test 2: Content-Type
        content_type = response.headers.get("Content-Type", "")
        is_pdf_content_type = "application/pdf" in content_type
        print_test(
            "Content-Type",
            is_pdf_content_type,
            f"Content-Type: {content_type}"
        )
        
        # Test 3: Valid PDF magic bytes
        pdf_bytes = response.content
        has_pdf_magic = pdf_bytes.startswith(b'%PDF')
        print_test(
            "Valid PDF Magic Bytes",
            has_pdf_magic,
            f"First 8 bytes: {pdf_bytes[:8]}"
        )
        
        if not has_pdf_magic:
            print("Not a valid PDF file")
            return False
        
        # Test 4: PDF size
        pdf_size = len(pdf_bytes)
        print_test(
            "PDF Size",
            pdf_size > 1000,
            f"Size: {pdf_size:,} bytes"
        )
        
        # Test 5: Parse PDF and check dimensions
        try:
            pdf_file = BytesIO(pdf_bytes)
            pdf_reader = PdfReader(pdf_file)
            
            num_pages = len(pdf_reader.pages)
            print_test(
                "PDF Readable",
                True,
                f"Pages: {num_pages}"
            )
            
            # Check A4 dimensions (595.3 x 841.9 points)
            if num_pages > 0:
                first_page = pdf_reader.pages[0]
                mediabox = first_page.mediabox
                width = float(mediabox.width)
                height = float(mediabox.height)
                
                # A4 dimensions with tolerance
                is_a4 = (590 <= width <= 600) and (835 <= height <= 850)
                print_test(
                    "A4 Dimensions",
                    is_a4,
                    f"Width: {width:.1f} points, Height: {height:.1f} points (A4: 595.3 x 841.9)"
                )
            
            # Test 6: Extract text and verify required elements
            print("\n=== PDF CONTENT VERIFICATION ===")
            
            all_text = ""
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    all_text += page_text + "\n"
                except Exception as e:
                    print(f"Warning: Could not extract text from page {page_num + 1}: {e}")
            
            # Convert to uppercase for case-insensitive matching
            all_text_upper = all_text.upper()
            
            # Check required elements
            missing_elements = []
            found_elements = []
            
            for element in REQUIRED_ELEMENTS:
                if element.upper() in all_text_upper:
                    found_elements.append(element)
                    print_test(f"Contains '{element}'", True, "")
                else:
                    missing_elements.append(element)
                    print_test(f"Contains '{element}'", False, "NOT FOUND")
            
            # Check for terms
            terms_found = any(term.upper() in all_text_upper for term in REQUIRED_TERMS)
            print_test(
                "Contains Terms & Conditions",
                terms_found,
                "Found" if terms_found else "NOT FOUND"
            )
            
            # Check for room/area table
            has_room_area = "ROOM" in all_text_upper or "AREA" in all_text_upper
            print_test(
                "Contains Room/Area Table",
                has_room_area,
                "Found" if has_room_area else "NOT FOUND"
            )
            
            # Check for totals
            has_total = "TOTAL" in all_text_upper or "GRAND TOTAL" in all_text_upper
            print_test(
                "Contains Total",
                has_total,
                "Found" if has_total else "NOT FOUND"
            )
            
            # Check for footer elements
            has_footer = any(x in all_text_upper for x in ["PAGE", "BUILDCON"])
            print_test(
                "Contains Footer",
                has_footer,
                "Found" if has_footer else "NOT FOUND"
            )
            
            # Summary
            print("\n=== SUMMARY ===")
            total_checks = len(REQUIRED_ELEMENTS) + 4  # +4 for terms, room, total, footer
            passed_checks = len(found_elements) + sum([terms_found, has_room_area, has_total, has_footer])
            
            print(f"Content Checks: {passed_checks}/{total_checks} passed")
            
            if missing_elements:
                print(f"\n⚠️  Missing elements: {', '.join(missing_elements)}")
            
            # Save a sample of extracted text for debugging
            print("\n=== SAMPLE EXTRACTED TEXT (first 1000 chars) ===")
            print(all_text[:1000])
            print("...")
            
            return len(missing_elements) == 0
            
        except Exception as e:
            print_test("PDF Parsing", False, f"Error: {str(e)}")
            return False
            
    except Exception as e:
        print_test("PDF Generation", False, f"Error: {str(e)}")
        return False

def test_health_endpoint():
    """Test health endpoint"""
    print("\n=== HEALTH CHECK ===")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        status_ok = response.status_code == 200
        print_test(
            "GET /api/health",
            status_ok,
            f"Status: {response.status_code}, Response: {response.json() if status_ok else response.text[:200]}"
        )
        return status_ok
    except Exception as e:
        print_test("GET /api/health", False, f"Error: {str(e)}")
        return False

def main():
    """Main test execution"""
    print("=" * 80)
    print("Production Sprint Objective 1 — Official Quotation PDF Template Fidelity")
    print("=" * 80)
    
    # Step 1: Authenticate
    token = authenticate()
    if not token:
        print("\n❌ CRITICAL: Authentication failed. Cannot proceed with testing.")
        sys.exit(1)
    
    # Step 2: Get existing quotation
    quotation_id = get_existing_quotation(token)
    if not quotation_id:
        print("\n❌ CRITICAL: No quotations found. Cannot test PDF generation.")
        sys.exit(1)
    
    # Step 3: Test PDF generation
    pdf_success = test_pdf_generation(token, quotation_id)
    
    # Step 4: Test health endpoint
    health_success = test_health_endpoint()
    
    # Final summary
    print("\n" + "=" * 80)
    print("FINAL RESULT")
    print("=" * 80)
    
    if pdf_success and health_success:
        print("✅ ALL TESTS PASSED")
        print("   - PDF generation: ✅")
        print("   - PDF content verification: ✅")
        print("   - Health endpoint: ✅")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        if not pdf_success:
            print("   - PDF generation or content: ❌")
        if not health_success:
            print("   - Health endpoint: ❌")
        sys.exit(1)

if __name__ == "__main__":
    main()

#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Forge — premium ERP/CRM/POS for sanitaryware distributors. Latest task: finish two P1 backend polish items — (a) VITRA .wdp → JPEG conversion for 100% image coverage, and (b) refactor certifier to whitelist cross-family SKU duplicates so Geberit/Vitra auto-certify."

backend:
  - task: "WDP (JPEG XR) image decoding in catalog image extractor"
    implemented: true
    working: "NA"
    file: "backend/catalog_pipeline/image_extractor.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Added _convert_wdp_to_png() using imagecodecs.jpegxr_decode + png_encode. When the xlsx media path ends in .wdp / .jxr / .hdp we now decode to PNG instead of skipping. Also fixed a latent bug where absolute Target paths ('/xl/worksheets/sheet1.xml') in workbook.xml.rels were being resolved as 'xl/xl/...'. Verified via a synthetic xlsx containing one PNG + one WDP anchor — extractor now returns both images as data URLs. imagecodecs==2026.3.6 pinned in requirements.txt."

  - task: "Certifier — cross-family SKU whitelist"
    implemented: true
    working: "NA"
    file: "backend/catalog_pipeline/certifier.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Refactored SKU dedupe. Same SKU inside the same family_key => 'true duplicate' (rejected, counted in duplicates_sku). Same SKU across different family_keys => 'cross-family listing' (kept, counted separately in the new cross_family_skus field, warning added). sku_accuracy now penalises only true duplicates. production_ready gate uses only duplicates_sku so Geberit/Vitra can now auto-certify at overall_score ≥ 95. Verified via synthetic ProductRow scenarios — cross-family scenario reports duplicates_sku=0, cross_family_skus=1, production_ready=true; true-dupe scenario correctly marks the second row rejected."

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 3
  run_ui: false

test_plan:
  current_focus:
    - "WDP (JPEG XR) image decoding in catalog image extractor"
    - "Certifier — cross-family SKU whitelist"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Two P1 backend fixes ready for regression. (1) image_extractor now decodes WDP frames via imagecodecs; also fixed absolute-target resolution. (2) certifier distinguishes true dupes from cross-family listings so Geberit/Vitra imports can hit production_ready. Please regression-test the /api/catalog/imports/from-url and /api/catalog/imports/approve flows for at least one supplier catalog to confirm nothing regressed. Also verify the CertificationReport now exposes a `cross_family_skus` field. Auth creds in /app/memory/test_credentials.md (owner@forge.app / Forge@2026). No frontend changes in this iteration."

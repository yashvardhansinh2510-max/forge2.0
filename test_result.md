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

user_problem_statement: "Forge — premium ERP/CRM/POS for sanitaryware distributors. Current phase (1A): Complete the Quotation Builder 2.0 to feel world-class — comprehensive undo/redo, drag-and-drop reordering, product variant chips, and alternate swap. Prior P1 backend polish (VITRA WDP and cross-family SKU whitelist) already shipped in iteration 3."

backend:
  - task: "WDP (JPEG XR) image decoding in catalog image extractor"
    implemented: true
    working: true
    file: "backend/catalog_pipeline/image_extractor.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Added _convert_wdp_to_png() using imagecodecs.jpegxr_decode + png_encode; extractor also handles absolute `/xl/...` targets. imagecodecs==2026.3.6 pinned."
        - working: true
          agent: "testing"
          comment: "Iteration 3: 13 new + 43 existing tests green. WDP → PNG round-trip verified end-to-end."

  - task: "Certifier — cross-family SKU whitelist"
    implemented: true
    working: true
    file: "backend/catalog_pipeline/certifier.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Same SKU inside the same family_key => true duplicate (rejected). Cross-family listings kept and counted in the new cross_family_skus field. production_ready gate only considers true duplicates."
        - working: true
          agent: "testing"
          comment: "Iteration 3: both spec scenarios pass; to_public() exposes cross_family_skus and preserves all 21 legacy keys."

  - task: "GET /api/products/{id}/alternates smart-mix ranking"
    implemented: true
    working: "NA"
    file: "backend/routes/catalog_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "New endpoint returning alternates in three ranked tiers within one response: tier 1 = same brand + same category + same 2-word name prefix (approximates family); tier 2 = same brand + same category; tier 3 = same category cross-brand. Ranking key is (tier, -user_usage_count, price). Response shape: {source_product_id, items: [Product], tiers: {family, brand_category, category}}. 404 when source product missing. Depends on get_current_user (staff JWT). Verified live via the swap sheet — a Hansgrohe basin mixer returned 10 items with same-brand alternates first, then cross-brand."

frontend:
  - task: "Quotation Builder 2.0 Phase 1A — undo/redo, DnD, variants, alternates"
    implemented: true
    working: "NA"
    file: "frontend/app/(admin)/quotations/new.tsx, frontend/src/hooks/useHistory.ts, frontend/app/_layout.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Rewritten builder. All mutable state (customerId, lines, rooms, collapsedRooms, activeRoom, notes, projectDiscount, categoryDiscounts) consolidated into one BuilderState managed by useHistory (200-step bounded, 800ms coalescing on text inputs). Every mutation — addFromProduct, updateLine (qty/rate/desc/discount), removeLine, duplicateLine, moveLineToNextRoom, addRoom / renameRoom / duplicateRoom / deleteRoom, setProjectDiscount, setCategoryDiscount, setCustomer, commitSwap, onRoomDragEnd, onLinesDragEnd — pushes to history. Collapse toggles + active-room switches use skipHistory:true (pure UI state). DraggableFlatList powers a horizontal room-chip row and a vertical mixed list of {room-header, line} rows so dragging a line across a header re-parents its room automatically. Variant chip strip on picker rows shows finish/colour + swatch dot + price delta when it differs. Swap-alternate bottom sheet preserves qty, discount, tax, notes, description, room. Web keyboard: Cmd/Ctrl+Z / Cmd/Ctrl+Shift+Z / Ctrl+Y wired via useUndoRedoShortcuts, Cmd/Ctrl+K → focus search. GestureHandlerRootView wraps the root layout for DnD on native. Manually verified in the desktop viewport (1280×900) and the mobile viewport (390×844) — add/undo/redo/cmd+z/cmd+shift+z/swap-sheet all working, autosave still persists silently as before."

metadata:
  created_by: "main_agent"
  version: "1.2"
  test_sequence: 4
  run_ui: true

test_plan:
  current_focus:
    - "GET /api/products/{id}/alternates smart-mix ranking"
    - "Quotation Builder 2.0 Phase 1A — undo/redo, DnD, variants, alternates"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Iteration 3 (backend catalog fixes) shipped and green. Now iteration 4 — Quotation Builder 2.0 Phase 1A. Please regression-test both the new alternates endpoint and the new builder screen. Backend: verify /api/products/{id}/alternates returns 200 with the shape {source_product_id, items, tiers}, that items respect the 3-tier ordering, and that 404 is returned for a missing source id. Frontend: on the /(admin)/quotations/new screen — add products, use both button + keyboard undo/redo (cmd+z, cmd+shift+z), open the swap sheet from a line's swap icon, drag-reorder items via the menu handle, drag-reorder rooms via the room chip. History depth is shown as `N steps` in the header subtitle. Credentials in /app/memory/test_credentials.md (owner@forge.app / Forge@2026)."

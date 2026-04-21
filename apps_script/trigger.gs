/**
 * Immo AI — Google Apps Script Webhook Trigger
 *
 * Setup instructions:
 *  1. Open your Google Spreadsheet.
 *  2. Extensions → Apps Script → paste this code.
 *  3. Set the configuration constants below.
 *  4. Run setupTrigger() once to install the onEdit trigger.
 *  5. Authorize the script when prompted.
 *
 * How it works:
 *  - When a new row is added to "Exposé-Inputs" with status = "pending",
 *    it calls the Immo AI Flask webhook /api/automation/trigger.
 *  - The Flask server then runs the full automation pipeline for that row.
 */

// ── Configuration ─────────────────────────────────────────────────────────────
var IMMOAI_BASE_URL = "https://your-immo-ai-server.com"; // e.g. https://immo-ai.example.com
var WEBHOOK_SECRET  = "";       // Must match AUTOMATION_WEBHOOK_SECRET in .env
var ADMIN_SESSION_KEY = "";     // IMMOAI access key (from localStorage in browser)
var EXPOSE_SHEET_NAME = "Exposé-Inputs";
var STATUS_COL_INDEX  = 17;     // Column Q (1-based) = status field


// ── Trigger installation ──────────────────────────────────────────────────────

function setupTrigger() {
  // Remove existing triggers to avoid duplicates
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === "onSheetEdit") {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger("onSheetEdit")
    .forSpreadsheet(SpreadsheetApp.getActiveSpreadsheet())
    .onEdit()
    .create();
  Logger.log("Trigger installed: onSheetEdit");
}


// ── Edit handler ──────────────────────────────────────────────────────────────

function onSheetEdit(e) {
  try {
    var sheet = e.source.getActiveSheet();
    if (sheet.getName() !== EXPOSE_SHEET_NAME) return;

    var range = e.range;
    var row = range.getRow();
    if (row <= 1) return; // skip header row

    // Check if status column was set to "pending"
    var statusCell = sheet.getRange(row, STATUS_COL_INDEX);
    var status = statusCell.getValue().toString().trim().toLowerCase();

    if (status === "pending") {
      Logger.log("New pending row detected: row " + row + " — triggering pipeline");
      triggerPipeline();
    }
  } catch (err) {
    Logger.log("onSheetEdit error: " + err.message);
  }
}


// ── Webhook call ──────────────────────────────────────────────────────────────

function triggerPipeline() {
  var url = IMMOAI_BASE_URL + "/api/automation/trigger";

  var options = {
    method: "POST",
    contentType: "application/json",
    payload: JSON.stringify({ source: "apps_script" }),
    headers: {
      "X-Access-Key": ADMIN_SESSION_KEY,
      "X-Webhook-Secret": WEBHOOK_SECRET
    },
    muteHttpExceptions: true,
    followRedirects: true
  };

  try {
    var response = UrlFetchApp.fetch(url, options);
    var code = response.getResponseCode();
    var body = response.getContentText();
    Logger.log("Webhook response " + code + ": " + body);

    if (code !== 200) {
      Logger.log("WARNING: Pipeline trigger returned non-200: " + code);
    }
  } catch (err) {
    Logger.log("ERROR calling webhook: " + err.message);
  }
}


// ── Manual test ───────────────────────────────────────────────────────────────

function testTrigger() {
  Logger.log("Testing webhook call...");
  triggerPipeline();
  Logger.log("Done. Check logs above for response.");
}

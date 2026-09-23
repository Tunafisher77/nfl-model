/** NFL Wednesday delivery. Replace the existing weekly mailer file with this file. */
var NFL_GAME_TAB = 'NFL Game Email Summary';
var NFL_TD_TAB = 'NFL TD Email Summary';
var NFL_PROPS_TAB = 'NFL Props Email Summary';
var NFL_RECOVERY_HANDLER = 'runNflWednesdayEmailChecks';

function runNflWednesdayEmailChecks() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return;
  try {
    sendNflReportIfFresh_(NFL_GAME_TAB, 'NFL_GAME_EMAIL_SENT_WEEK', 'Weekly NFL Game Evaluations');
    sendNflReportIfFresh_(NFL_TD_TAB, 'NFL_TD_EMAIL_SENT_WEEK', 'Weekly NFL Touchdown Candidates');
    sendNflReportIfFresh_(NFL_PROPS_TAB, 'NFL_PROPS_EMAIL_SENT_WEEK', 'Weekly NFL Player Yardage Props');
  } finally { lock.releaseLock(); }
}
function sendTestNflGameEmail() { sendNflReport_(NFL_GAME_TAB, '[TEST] Weekly NFL Game Evaluations'); }
function sendTestNflTouchdownEmail() { sendNflReport_(NFL_TD_TAB, '[TEST] Weekly NFL Touchdown Candidates'); }
function sendTestNflYardageEmail() { sendNflReport_(NFL_PROPS_TAB, '[TEST] Weekly NFL Player Yardage Props'); }

function installNflWednesdayEmailTriggers() {
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (trigger.getHandlerFunction() === NFL_RECOVERY_HANDLER) ScriptApp.deleteTrigger(trigger);
  });
  [6, 7, 8, 9, 10, 11, 12].forEach(function(hour) {
    ScriptApp.newTrigger(NFL_RECOVERY_HANDLER).timeBased()
      .onWeekDay(ScriptApp.WeekDay.WEDNESDAY).atHour(hour).create();
  });
}
function sendNflReportIfFresh_(tabName, propertyName, reportTitle) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(tabName);
  if (!sheet) return false;
  var metadata = getNflMetadata_(sheet.getDataRange().getDisplayValues());
  var easternToday = Utilities.formatDate(new Date(), 'America/New_York', 'yyyy-MM-dd');
  if (!metadata.scheduleDate || metadata.scheduleDate !== easternToday || !metadata.season || !metadata.week) return false;
  var weekKey = metadata.season + '-' + metadata.week;
  var properties = PropertiesService.getScriptProperties();
  if (properties.getProperty(propertyName) === weekKey) return false;
  sendNflReport_(tabName, reportTitle + ' — ' + metadata.season + ' Week ' + metadata.week);
  properties.setProperty(propertyName, weekKey);
  return true;
}
function sendNflReport_(tabName, subject) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(tabName);
  if (!sheet) throw new Error(tabName + ' tab not found.');
  var recipient = Session.getEffectiveUser().getEmail();
  if (!recipient) throw new Error('Unable to determine the trigger owner email address.');
  var values = sheet.getDataRange().getDisplayValues();
  MailApp.sendEmail({to: recipient, subject: subject, body: nflUnifiedText_(values),
    htmlBody: nflUnifiedHtml_(values), name: 'NFL Weekly Model'});
}
function getNflMetadata_(values) {
  var metadata = {scheduleDate: '', season: '', week: ''};
  values.forEach(function(row) {
    if (row[0] === 'Schedule Date Used') metadata.scheduleDate = row[1];
    if (row[0] === 'Season') metadata.season = row[1];
    if (row[0] === 'Week') metadata.week = row[1];
  });
  return metadata;
}
function nflUnifiedText_(values) {
  return values.filter(function(row) { return row[0] || row[1]; })
    .map(function(row) { return row[1] ? row[0] + ': ' + row[1] : row[0]; }).join('\n');
}
function nflUnifiedHtml_(values) {
  var title = values.length && values[0][0] ? values[0][0] : 'NFL Weekly Model';
  var html = '<div style="font-family:Arial,sans-serif;max-width:760px;margin:auto;color:#152238">' +
    '<div style="background:#123a63;color:#fff;padding:18px 22px;border-radius:8px 8px 0 0">' +
    '<h2 style="margin:0;font-size:23px">' + nflUnifiedEscape_(title) + '</h2></div>' +
    '<div style="border:1px solid #d7e0ea;border-top:0;padding:18px 22px">';
  var metadata = {'Schedule Date Used':1, 'Season':1, 'Week':1, 'Season Type':1,
    'Generated':1, 'Model Policy':1, 'Roster Validation':1, 'Roster Source':1,
    'Roster Refreshed':1, 'Card Policy':1, 'TD Selection':1, 'Availability Note':1,
    'Score Note':1};
  for (var i = 1; i < values.length; i++) {
    var left = String(values[i][0] || '');
    var right = String(values[i][1] || '');
    if (!left && !right) { html += '<div style="height:9px"></div>'; continue; }
    var section = !right || left === 'All Games' || left === 'Touchdown Leaders' ||
      /^(Passing|Rushing|Receiving) Yards$/.test(left) || /^GAME \d+:/.test(left);
    var game = !section && (/^[A-Z]{2,3} at [A-Z]{2,3}$/.test(left) ||
      / — [A-Z]{2,3} (at|vs) [A-Z]{2,3}$/.test(left));
    if (section) {
      html += '<div style="margin:20px 0 8px;padding:9px 12px;background:#eaf1f7;border-left:4px solid #2d6ca2">' +
        '<strong style="color:#123a63">' + nflUnifiedEscape_(left) + '</strong>' +
        (right ? '<div style="font-size:13px;color:#536273;margin-top:3px">' + nflUnifiedEscape_(right) + '</div>' : '') + '</div>';
    } else if (metadata[left]) {
      html += '<div style="font-size:12px;color:#536273;line-height:1.5"><strong>' +
        nflUnifiedEscape_(left) + ':</strong> ' + nflUnifiedEscape_(right) + '</div>';
    } else {
      html += '<div style="padding:9px 12px;margin:5px 0;border:1px solid #e1e7ed;' +
        (game ? 'border-left:4px solid #2d6ca2;background:#f5f8fb' : 'border-radius:4px') + '">' +
        '<strong>' + nflUnifiedEscape_(left) + '</strong>' +
        (right ? '<div style="font-size:13px;color:#536273;margin-top:3px">' + nflUnifiedEscape_(right) + '</div>' : '') + '</div>';
    }
  }
  return html + '<p style="margin-top:24px;font-size:12px;color:#6b7785">Statistics-only analysis. No sportsbook odds, lines, implied probabilities, or market influence are used.</p></div></div>';
}
function nflUnifiedEscape_(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, function(char) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char];
  });
}
function buildNflReportHtml_(values) { return nflUnifiedHtml_(values); }
function escapeNflHtml_(value) { return nflUnifiedEscape_(value); }
function resetNflEmailSentFlagsOnce() {
  var properties = PropertiesService.getScriptProperties();
  properties.deleteProperty('NFL_GAME_EMAIL_SENT_WEEK');
  properties.deleteProperty('NFL_TD_EMAIL_SENT_WEEK');
  properties.deleteProperty('NFL_PROPS_EMAIL_SENT_WEEK');
  Logger.log('NFL weekly email sent flags cleared.');
}

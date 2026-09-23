var NFL_BEST_CARD_TAB = 'NFL Best Card Email Summary';
var NFL_BEST_CARD_SENT_WEEK = 'NFL_BEST_CARD_SENT_WEEK';

function runNflBestCardWednesdayCheck() {
  var zone = 'America/Los_Angeles';
  var now = new Date();
  if (Utilities.formatDate(now, zone, 'u') !== '3') return;
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return;
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(NFL_BEST_CARD_TAB);
    if (!sheet || sheet.getLastRow() < 2) return;
    var values = sheet.getDataRange().getDisplayValues();
    var season = findNflBestCardValue_(values, 'Season');
    var week = findNflBestCardValue_(values, 'Week');
    if (!season || !week) return;
    var key = season + '-W' + week;
    var props = PropertiesService.getScriptProperties();
    if (props.getProperty(NFL_BEST_CARD_SENT_WEEK) === key) return;
    MailApp.sendEmail({to: Session.getEffectiveUser().getEmail(),
      subject: 'Weekly NFL Best Card — ' + season + ' Week ' + week,
      htmlBody: nflUnifiedHtml_(values), body: nflUnifiedText_(values), name: 'NFL Weekly Model'});
    props.setProperty(NFL_BEST_CARD_SENT_WEEK, key);
  } finally { lock.releaseLock(); }
}

function findNflBestCardValue_(values, label) {
  for (var i = 0; i < values.length; i++) if (values[i][0] === label) return values[i][1];
  return '';
}

function escapeNflBestCard_(value) {
  return String(value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function installNflBestCardWednesdayTriggers() {
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'runNflBestCardWednesdayCheck') ScriptApp.deleteTrigger(trigger);
  });
  [6, 7, 8, 9, 10, 11, 12].forEach(function(hour) {
    ScriptApp.newTrigger('runNflBestCardWednesdayCheck').timeBased().onWeekDay(ScriptApp.WeekDay.WEDNESDAY)
      .atHour(hour).nearMinute(5).inTimezone('America/Los_Angeles').create();
  });
}

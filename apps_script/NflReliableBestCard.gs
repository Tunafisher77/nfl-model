/** Content-aware reliability helpers for NFL Best Card delivery. */
function runNflReliableBestCardWednesdayCheck() {
  var zone = 'America/Los_Angeles';
  if (Utilities.formatDate(new Date(), zone, 'u') !== '3') return;
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
    var fingerprint = nflContentFingerprint_(values);
    var fpKey = 'NFL_BEST_CARD_CONTENT_' + key;
    var previous = props.getProperty(fpKey);
    if (previous === fingerprint) return;
    MailApp.sendEmail({to: props.getProperty('NFL_EMAIL_TO') || Session.getEffectiveUser().getEmail(),
      subject: (previous ? '[UPDATED] ' : '') + 'Weekly NFL Best Card — ' + season + ' Week ' + week,
      htmlBody: nflUnifiedHtml_(values), body: nflUnifiedText_(values), name: 'NFL Weekly Model'});
    props.setProperty(NFL_BEST_CARD_SENT_WEEK, key);
    props.setProperty(fpKey, fingerprint);
  } finally { lock.releaseLock(); }
}
function installNflReliableBestCardTriggers() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'runNflBestCardWednesdayCheck' ||
        t.getHandlerFunction() === 'runNflReliableBestCardWednesdayCheck') ScriptApp.deleteTrigger(t);
  });
  [6,7,8,9,10,11,12].forEach(function(hour) {
    ScriptApp.newTrigger('runNflReliableBestCardWednesdayCheck').timeBased()
      .onWeekDay(ScriptApp.WeekDay.WEDNESDAY).atHour(hour).nearMinute(5)
      .inTimezone('America/Los_Angeles').create();
  });
}

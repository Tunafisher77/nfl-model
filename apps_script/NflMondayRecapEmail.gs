/**
 * Additive NFL Monday recap email.
 *
 * Paste this entire file into a NEW Apps Script .gs file in the spreadsheet-bound
 * project. Run installNflMondayRecapTrigger() once and approve permissions.
 */

var NFL_RECAP_SHEET = 'NFL Weekly Recap Email Summary';

function sendNflMondayRecapEmail() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return false;

  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(NFL_RECAP_SHEET);
    if (!sheet || sheet.getLastRow() < 2) {
      throw new Error('NFL recap summary is not ready.');
    }

    var values = sheet.getDataRange().getDisplayValues();
    var season = findNflRecapValue_(values, 'Season');
    var week = findNflRecapValue_(values, 'Week');
    var generated = findNflRecapValue_(values, 'Generated');
    if (!season || !week || !generated) {
      throw new Error('NFL recap season/week/generated metadata is missing.');
    }

    var easternToday = Utilities.formatDate(
      new Date(),
      'America/New_York',
      'yyyy-MM-dd'
    );
    if (generated.indexOf(easternToday) !== 0) {
      console.log(
        'NFL recap not sent: summary is stale. Expected ' +
        easternToday + ', generated ' + generated
      );
      return false;
    }

    var sentKey = 'NFL_RECAP_SENT_' + season + '_' + week;
    var properties = PropertiesService.getScriptProperties();
    if (properties.getProperty(sentKey) === 'true') {
      return false;
    }

    var recipient = properties.getProperty('NFL_EMAIL_TO') ||
      Session.getEffectiveUser().getEmail();
    if (!recipient) {
      throw new Error(
        'Set the NFL_EMAIL_TO script property to the destination email address.'
      );
    }

    var subject = 'NFL Week ' + week + ' Picks Recap — ' + season;
    MailApp.sendEmail({
      to: recipient,
      subject: subject,
      body: nflUnifiedText_(values),
      htmlBody: nflUnifiedHtml_(values),
      name: 'NFL Weekly Model'
    });
    properties.setProperty(sentKey, 'true');
    return true;
  } finally {
    lock.releaseLock();
  }
}

function sendNflMondayRecapEmailIfFresh() {
  return sendNflMondayRecapEmail();
}

function installNflMondayRecapTrigger() {
  var handlers = [
    'sendNflMondayRecapEmail',
    'sendNflMondayRecapEmailIfFresh'
  ];
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (handlers.indexOf(trigger.getHandlerFunction()) !== -1) {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  [7, 9, 11, 13].forEach(function(hour) {
    ScriptApp.newTrigger('sendNflMondayRecapEmailIfFresh')
      .timeBased()
      .onWeekDay(ScriptApp.WeekDay.MONDAY)
      .atHour(hour)
      .nearMinute(15)
      .inTimezone('America/Los_Angeles')
      .create();
  });
}

function findNflRecapValue_(values, label) {
  for (var i = 0; i < values.length; i++) {
    if (values[i][0] === label) return values[i][1];
  }
  return '';
}


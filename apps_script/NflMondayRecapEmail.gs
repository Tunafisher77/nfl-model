/**
 * Additive NFL Monday recap email.
 *
 * Paste this entire file into a NEW Apps Script .gs file in the spreadsheet-bound
 * project. Run installNflMondayRecapTrigger() once and approve permissions.
 */

var NFL_RECAP_SHEET = 'NFL Weekly Recap Email Summary';

function sendNflMondayRecapEmail() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(NFL_RECAP_SHEET);
  if (!sheet || sheet.getLastRow() < 2) {
    throw new Error('NFL recap summary is not ready.');
  }

  var values = sheet.getDataRange().getDisplayValues();
  var season = findNflRecapValue_(values, 'Season');
  var week = findNflRecapValue_(values, 'Week');
  if (!season || !week) {
    throw new Error('NFL recap season/week metadata is missing.');
  }

  var sentKey = 'NFL_RECAP_SENT_' + season + '_' + week;
  var properties = PropertiesService.getScriptProperties();
  if (properties.getProperty(sentKey) === 'true') {
    return;
  }

  var recipient = properties.getProperty('NFL_EMAIL_TO') || Session.getEffectiveUser().getEmail();
  if (!recipient) {
    throw new Error('Set the NFL_EMAIL_TO script property to the destination email address.');
  }

  var subject = 'NFL Week ' + week + ' Picks Recap — ' + season;
  MailApp.sendEmail({
    to: recipient,
    subject: subject,
    body: nflRecapPlainText_(values),
    htmlBody: nflRecapHtml_(values),
    name: 'NFL Weekly Model'
  });
  properties.setProperty(sentKey, 'true');
}

function installNflMondayRecapTrigger() {
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'sendNflMondayRecapEmail') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  ScriptApp.newTrigger('sendNflMondayRecapEmail')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(7)
    .nearMinute(15)
    .inTimezone('America/Los_Angeles')
    .create();
}

function findNflRecapValue_(values, label) {
  for (var i = 0; i < values.length; i++) {
    if (values[i][0] === label) return values[i][1];
  }
  return '';
}

function nflRecapPlainText_(values) {
  return values.filter(function(row) {
    return row[0] || row[1];
  }).map(function(row) {
    return row[1] ? row[0] + ': ' + row[1] : row[0];
  }).join('\n');
}

function nflRecapHtml_(values) {
  var html = '<div style="font-family:Arial,sans-serif;max-width:760px;color:#172033">';
  for (var i = 0; i < values.length; i++) {
    var left = values[i][0] || '';
    var right = values[i][1] || '';
    if (!left && !right) {
      html += '<div style="height:10px"></div>';
    } else if (left === 'NFL Weekly Picks Recap') {
      html += '<h1 style="font-size:24px;margin:0 0 12px;color:#0b3d71">' + nflRecapEscape_(left) + '</h1>';
    } else if (!right) {
      html += '<h2 style="font-size:18px;margin:18px 0 6px;padding-bottom:5px;border-bottom:2px solid #0b3d71">' + nflRecapEscape_(left) + '</h2>';
    } else {
      var color = right.indexOf('HIT') === 0 ? '#16794b' : (right.indexOf('MISS') === 0 ? '#b42318' : '#596579');
      html += '<div style="padding:7px 4px;border-bottom:1px solid #e6e9ee"><strong>' +
        nflRecapEscape_(left) + '</strong><br><span style="color:' + color + '">' +
        nflRecapEscape_(right) + '</span></div>';
    }
  }
  return html + '</div>';
}

function nflRecapEscape_(value) {
  return String(value).replace(/[&<>"']/g, function(char) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char];
  });
}

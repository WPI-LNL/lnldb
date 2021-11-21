
Package.describe({
  name    : 'semantic:ui-checkbox',
  summary : 'Semantic UI - Checkbox: Single component release',
  version : '2.2.10',
  git     : 'git://github.com/Semantic-Org/UI-Checkbox.git',
});

Package.onUse(function(api) {
  api.versionsFrom('1.0');
  api.addFiles([
    'checkbox.css',
    'checkbox.js'
  ], 'client');
});

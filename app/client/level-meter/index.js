var reactive = require('reactive');
var template = require('./template');
var $        = require('jquery');

// Make it work with component/models
reactive.get(function (obj, prop) {
  return obj.get(prop);
});
reactive.set(function (obj, prop, val) {
  return obj.set(prop, val);
});

module.exports = function ($el, model) {
  $el.append($(template));
  var view = reactive($el[0], model);

  view.bind('percent-complete', function (el) {
    function update (rounds) {
      var percentComplete = rounds / model.rounds() * 100;
      $(el).css('width',  percentComplete + '%');
    }
    model.on('change current_round', update);
    update(model.current_round());
  });
};
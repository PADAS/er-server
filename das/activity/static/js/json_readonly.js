;(function(window, document) {
    function setup() {
        var widgets = document.querySelectorAll('*[class="json-readonly"][data-jsonreadonly]');

        for (var i = 0; i < widgets.length; i++) {
            var code = widgets[i].querySelector('.jsonr code'),
                prettyJSON = JSON.stringify(JSON.parse(code.dataset.raw), null, 2),
                prettyHTML = Prism.highlight(prettyJSON, Prism.languages.json);

            console.log(prettyHTML)

            code.innerHTML = prettyHTML;
        }
    }

    // function DOMReady(a,b,c){b=document,c='addEventListener';b[c]?b[c]('DOMContentLoaded',a):window.attachEvent('onload',a)}
    // DOMReady(setup);
    window.addEventListener('DOMContentLoaded',function () {
    //your code here
        setup()
});
}(window, document));
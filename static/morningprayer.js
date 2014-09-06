$(document).ready(function() {
    var today;

    $("#setting-gear").click(function() {
        $("#settings").toggle();
    });

//http://stackoverflow.com/questions/3066586/get-string-in-yyyymmdd-format-from-js-date-object
    var to_yyyy_mm_dd = function(date) {
        var yyyy = date.getFullYear().toString();
        var mm = (date.getMonth()+1).toString(); // getMonth() is zero-based
        var dd = date.getDate().toString();
        return yyyy + "-" + (mm[1]?mm:"0"+mm[0]) + "-" + (dd[1]?dd:"0"+dd[0]); // padding
     };

    if ($('#psalms').html().trim() === "Getting today's reading...") {
        if (location.search === "") {
            current_date = to_yyyy_mm_dd(new Date());
        } else {
            current_date = location.search.replace(/\?date=(\d{4}-\d{2}-\d{2})/, "$1")
        }

        $.getJSON('/prayer/morningprayer/readings.json?date=' + current_date)
            .done(function(data){
                $('#psalms').html(data.psalms);
                $("#reading0").html(data.reading0);
                $("#reading1").html(data.reading1);
                $("#reading2").html(data.reading2);
                $("#copyright").html(data.copyright);
            })
            .fail(function(e){
                $('#psalms').html('<p>Sorry, we had an error in' +
                 ' loading the readings... you can try refreshing the page.</p>');
            });
    }
});

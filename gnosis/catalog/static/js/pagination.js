function pagination(current, first, last, current_path) {

    var $page_items = $('.num_item');
    var path = '?page=';

    if (current_path.indexOf('?keywords=') !== -1) {
        current_path = current_path.replace('&amp;', '&');
        if (current_path.indexOf('&page=') !== -1) {
            path = current_path.slice(0, -1)
        } else {
            path = current_path;
            path += '&page=';
        }
    }


    if (last > 5) {
        if (current <= first + 2) {
            $($page_items).each(function (index) {
                if (index === 4) {
                    $(this).children('a').text(last).attr('href', path + last);
                } else {
                    $(this).children('a').text(index + 1).attr('href', path + (index + 1));
                    if (current === index + 1) {
                        $(this).addClass('active');
                    }
                }
            })
        } else if (current >= last - 2) {
            $($page_items).each(function (index) {
                if (index === 0) {
                    $(this).children('a').text(first).attr('href', path + first);
                } else {
                    $(this).children('a').text(last - 4 + index).attr('href', path + (last - 4 + index));
                    if (current === last - 4 + index) {
                        $(this).addClass('active');
                    }
                }
            })
        } else {
            $page_items.eq(2).addClass('active');
        }

        if (current <= first + 2) {
            $('.first_ellipsis').css('display', 'none');
        }

        if (current >= last - 2) {
            $('.last_ellipsis').css('display', 'none');
        }

    } else {
        $($page_items).each(function (index) {
            if (index + 1 <= last) {
                $(this).children('a').text(index + 1).attr('href', path + (index + 1));
                if (current === index + 1) {
                    $(this).addClass('active');
                }
            } else {
                $(this).css('display', 'none');
            }
        });
        $('.first_ellipsis').css('display', 'none');
        $('.last_ellipsis').css('display', 'none');

    }

    /************** hide/show elements depending on current display width **************/
    if ($(window).width() <= 678) {
        $('.mobile').css('display', '');
        $('.desktop').css('display', 'none');
    } else {
        $('.mobile').css('display', 'none');
        $('.desktop').css('display', '');
    }

    $(window).resize(function () {
        if ($(window).width() <= 678) {
            $('.mobile').css('display', '');
            $('.desktop').css('display', 'none');
        } else {
            $('.mobile').css('display', 'none');
            $('.desktop').css('display', '');
        }
    });
}

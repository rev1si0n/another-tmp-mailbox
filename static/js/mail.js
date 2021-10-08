(function() {
	var clipboard = new Clipboard('.copyable');
	clipboard.on('success', function(e) {
    		console.info('copy address:', e.text);
		$.uiAlert({
  			textHead: '复制成功',
  			text: e.text,
  			bgcolor: '#2ecc71',
			textcolor: '#fff',
  			position: 'top-right',
  			time: 1.2
  		});
	});
	clipboard.on('error', function(e) {
		$.uiAlert({
  			textHead: '复制失败',
  			text: '无法复制文本，请手动复制',
  			bgcolor: '#e74c3c',
			textcolor: '#fff',
  			position: 'top-right',
  			time: 1.2
  		});
	});
	document.querySelector('iframe').addEventListener('load', function() {
		var iframeBody = this.contentWindow.document.body;
		var height = Math.max(iframeBody.scrollHeight, iframeBody.offsetHeight);
		//iframeBody = this.contentDocument.body;
		//height = Math.max(height, iframeBody.offsetHeight)
		//height = Math.max(height, iframeBody.scrollHeight)
		this.style.height = `${height}px`;
		console.log("iframe h: " + height)
	})
	UUID = null
	setAddress = function(uuid) {
		$("#address")[0].value = uuid + "@" + DOMAIN
		$('#address').parent().attr('data-clipboard-text', uuid + "@" + DOMAIN);
		$('#rss-link').attr('data-clipboard-text', (window.location.origin + window.location.pathname + "/mail/" + uuid + "/rss").replace(RegExp('//mail/', 'g'), "/mail/"));
	}
	adjustSize = function() {
		$("#content-iframe").height($("#content-iframe").contents().height())
	}
	showDetail = function(id) {
		$("#newtab").attr("href", "#")
		$("#newtab").attr("target", "")
		$.ajax({
        		type: "GET",
        		url: "/mail/" + UUID + "/" + id,
        		success: function(msg) {
				$("#subject").text("主题：" + msg.subject), $("#content-iframe")[0].src = '/mail/' + UUID + '/' + id + '/iframe'
				$("#newtab").attr("href", '/mail/' + UUID + '/' + id + '/show')
				$("#newtab").attr("target", "_blank")
        		},
        		error: function(msg) {
                		console.log(msg)
        		}
		})
	}
	setIntervalImmed = function(func, interval) {
		func(); return setInterval(func, interval)
	}
	$("#releaseAddress")[0].onclick  = function() {
		$.ajax({
		        type: "DELETE",
			dataType: "text",
		        url: "/user/" + UUID,
		        success: function(msg) {
				$.uiAlert({
  					textHead: '删除成功',
  					text: '邮箱及数据已删除，正在分配新邮箱',
  					bgcolor: '#e74c3c',
					textcolor: '#fff',
  					position: 'top-right',
  					time: 1.0
  				});
				setTimeout(function() {
        	        		window.location.reload()
				}, 1000)
		        },
		        error: function(msg) {
                		window.location.reload()
		        }
		})
	}
        $.ajax({
                type: "POST",
                url: "/user/",
                success: function(msg) {
			UUID = msg.uuid
                        setAddress(UUID)
                        setIntervalImmed(function () {
                                $.ajax({
                                        type: "GET",
                                        url: "/mail/" + UUID,
                                        success: function(msg) {
                                                $maillist = $("#maillist")
                                                $maillist[0].innerHTML = ""
						if (msg.length) {
                                                	for (var i = 0; i < msg.length; i++) {
	                                                	$tr = $('<tr id="mail-' + msg[i].id + '" onclick="showDetail(' + msg[i].id + ')">').data("", "");
                                                        	$tr
                                                        	.append($('<td>').text(msg[i].sender))
                                                        	.append($('<td>').text(msg[i].subject || '无主题'))
                                                        	.append($('<td>').text(msg[i].create_time))
                                                		$maillist.append($tr)
                                                	}
						} else {
							$("#maillist").html('<p style="margin: 1em 1em 1em 1em">暂无邮件可以显示。</p>')
						}
					},
                                        error: function(msg) {
                                                console.log(msg)
                                        }
                                })
                        }, 1.678*1000)
			setInterval(function() {
        			$.ajax({
                			type: "POST",
                			url: "/user/",
        			})
			}, 60*1000)
                },
                error: function(msg) {
                }
        })
})();


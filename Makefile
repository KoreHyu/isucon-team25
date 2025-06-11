.PHONY: init
init: webapp/sql/dump.sql.bz2 benchmarker/userdata/img

webapp/sql/dump.sql.bz2:
	cd webapp/sql && \
	curl -L -O https://github.com/catatsuy/private-isu/releases/download/img/dump.sql.bz2

benchmarker/userdata/img.zip:
	cd benchmarker/userdata && \
	curl -L -O https://github.com/catatsuy/private-isu/releases/download/img/img.zip

benchmarker/userdata/img: benchmarker/userdata/img.zip
	cd benchmarker/userdata && \
	unzip -qq -o img.zip


bench:
	sudo rm /var/log/mysql/mysql-slow.log
	sudo touch /var/log/mysql/mysql-slow.log && sudo chmod 777 /var/log/mysql/mysql-slow.log
	curl https://xnvvb925bl.execute-api.ap-northeast-1.amazonaws.com/

slow-query:
	sudo pt-query-digest /var/log/mysql/mysql-slow.log

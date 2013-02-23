히마와리 Himawari
=================

히마와리는 IRC 채널에 상주하면서 채널 사람들이 입력한 규칙에 따라 개드립을 쏟아내는 IRC 봇입니다. 한국어를 위해 설계되었지만 약간의 수정으로 다른 언어에도 대응 가능합니다. [특설 페이지](http://cosmic.mearie.org/f/himawari/)도 참고하세요.

Himawari is an IRC bot designed to say rants, generated by the rules specific to and customized by given IRC channel. It is designed for Korean language but also adaptable to other languages with appropriate fixes. See also the [special page](http://cosmic.mearie.org/f/himawari/) (Korean).


간단한 명령 목록
----------------

"히마와리"로 시작하는 호출 문법은 봇의 닉에 따라 달라질 수 있습니다. 아래에서 `<키>`는 한글로만 이루어진 공백 없는 문자열이나, 인자가 있는 값 읽기를 제외하고 빈 문자열이 될 수 있습니다.

* 봇 초대: IRC의 초대 기능을 사용하십시오.
* 값 추가: `\<키>: <값>`
	* 변경 명령과 혼동을 방지하기 위해 `<값>`에는 화살표가 들어갈 수 없습니다.
* 값 변경/삭제: `\<키>: <옛값> -> <새값>` 또는 '\<키>: <옛값> → <새값>`
	* 만약 `<옛값>`에 정확히 매칭되는 값은 없지만, 그 값을 포함하는 값이 정확히 하나 있으면 그 값의 해당하는 부분이 `<새값>`으로 바뀝니다.
	* 치환 후 저장될 값이 빈 문자열이면 해당 값은 삭제됩니다. 만약 그 값이 마지막 값이었다면 키도 함께 삭제됩니다.
* 값 읽기: `\<키>?` 또는 `\<키> <인자1> <인자2> ...?`
	* 인자가 있을 경우 `{$1}`, `{$2}`, ...에 순서대로 배당됩니다. (문법 참고)
* 값 목록 나열: `\<키>??`
* 키 목록 나열: `\모든키??`
	* 목록이 많은 경우 특설 페이지의 데이터베이스가 더 편리합니다.
* 문법 테스트: `\말해: <내용>`
	* 이 명령과 중복되기 때문에 `말해` 키에 값을 추가하는 것은 불가능합니다.
* 봇 종료: `히마와리, 나가` 또는 `히마와리, 꺼져`

다음 키는 봇의 메시지나 기타 특수한 목적으로 사용됩니다. 봇이 자동으로 사용한다는 점을 빼면 일반적인 값 읽기와 완벽하게 동일하게 처리되며, 문법도 쓸 수 있습니다.

* `저장후`: `{키}`에 `{값}`을 추가했을 때 출력됨 (원래는 출력하지 않음)
* `리셋후`: `{키}`에서 값을 삭제했을 때 출력됨 (원래는 출력하지 않음)
* `없는키`: `{키}`를 읽으려고 시도했으나 존재하지 않을 때 출력됨
* `도움말`: `\`로 시작되는 줄이 알려진 문법과 맞지 않을 때 출력됨
* `인사말`: 사용자 요청으로 채널에 들어왔을 때 출력됨
* `나갈때`: 사용자 요청으로 채널에서 나갈 때 퇴장 메시지로 출력됨
* `심심할때`: 임의의 주기로 랜덤하게 출력됨 (원래는 출력하지 않음)


간단한 문법 설명
----------------

* `{<키>}` 또는 `{<키><인덱스>}`는 해당하는 키의 값 중 아무 거나 무작위로 치환됩니다.
	* `<키>`가 존재하지 않거나, 재귀적으로 치환될 경우 빈 문자열을 사용합니다.
	* `<인덱스>`(숫자나 로마자로 이루어짐)는 같은 키가 여러 번 나올 때 같은 인덱스를 가진 키는 똑같은 값으로 치환되도록 합니다.
	* 만약 뒤에 알려진 조사가 띄어쓰기 없이 붙어 있을 경우, 치환되는 문자열에 맞춰서 조사도 바뀝니다.
	* 기본 템플릿(키가 빈 문자열)은 이 방법으로 호출할 수 없습니다.
* `{<최소값>-<최대값>}`은 주어진 범위의 숫자 중 아무 숫자나 선택해서 치환합니다.
	* 최소값과 최대값 앞에 `0`이 붙어 있을 경우 그 길이에 맞춰서 치환됩니다. 예를 들어 `{1-99}`는 한 자리 또는 두 자리일 수 있지만, `{01-99}`는 항상 두 자리입니다.
* `{$<번호>}`는 `\<키>?` 명령에서 인자가 주어졌을 경우 그 인자로 치환됩니다.
	* 인자가 없는 경우 빈 문자열로 치환됩니다.
	* 만약 뒤에 알려진 조사가 띄어쓰기 없이 붙어 있을 경우, 치환되는 문자열에 맞춰서 조사도 바뀝니다.

다음 키는 항상 고정되어 있으며 키 등록에 영향을 받지 않습니다.

* `{나}`: 봇의 닉으로 치환됨
* `{여기}`: 봇이 명령을 받은 채널명에서 `#`을 제외한 문자열로 치환됨
* `{이채널}`: 봇이 명령을 받은 채널명으로 치환됨
* `{너}`: 봇에게 명령을 내린 사람의 닉으로 치환됨


test_shrimple:
    .rtf "test_shrimple.bin"
    .assert~ faultcode=2, a0=69, uart="i am ur princess\r\n"

test_shrimprw:
    .rtf "test_shrimprw.bin", uart="y"
    .assert~ faultcode=2, a0=420

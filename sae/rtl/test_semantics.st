test_add:
    .init x1=3, x2=5
    add x3, x1, x2
    .assert x3=8

    .init x1=-1
    add x2, x0, x1
    .assert x2=-1

test_blah:

from tft_analyzer.perception.board.geometry import NormalizedPoint, board_centers, bench_centers

def test_board_geometry_is_4x7_and_ordered():
    left=tuple(NormalizedPoint(.3,.3+i*.1) for i in range(4)); right=tuple(NormalizedPoint(.7,.3+i*.1) for i in range(4))
    centers=board_centers(width=1000,height=1000,row_left=left,row_right=right,cols=7)
    assert len(centers)==28
    assert centers[0]==(0,0,300,300)
    assert centers[6]==(0,6,700,300)
    assert centers[-1]==(3,6,700,600)

def test_bench_geometry_has_nine_slots():
    centers=bench_centers(width=1000,height=1000,left=NormalizedPoint(.2,.8),right=NormalizedPoint(.8,.8),slots=9)
    assert len(centers)==9
    assert centers[0]==(0,200,800)
    assert centers[-1]==(8,800,800)

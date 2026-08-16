import numpy as np
from PIL import Image
from tft_analyzer.perception.board.features import classify_occupancy, occupancy_features, occupancy_score

def test_three_way_occupancy_thresholds():
    assert classify_occupancy(.20,empty_below=.38,occupied_above=.58)[0]=='empty'
    assert classify_occupancy(.48,empty_below=.38,occupied_above=.58)[0]=='uncertain'
    assert classify_occupancy(.75,empty_below=.38,occupied_above=.58)[0]=='occupied'

def test_textured_patch_scores_higher_than_flat_patch():
    flat=Image.fromarray(np.full((80,80,3),40,dtype=np.uint8))
    arr=np.zeros((80,80,3),dtype=np.uint8)
    arr[::2,:,0]=220; arr[:,::3,1]=180; arr[20:60,20:60,2]=230
    textured=Image.fromarray(arr)
    assert occupancy_score(occupancy_features(textured)) > occupancy_score(occupancy_features(flat))

# 
#           DFC Script 
# ============================= 
#   Description: 
#          Date: 2026-07-24 16:19:57
#       Version: Wranger 4.4.34.24527
# 
    S_1 = theModel.createSect( sectionName = "S_1");
    theModel.setSecCoordSys( id = S_1.id, orig = [0.00 , 0.00 , 0.00] , xDir = [1.00,0.00,0.00] , yDir =[0.00,1.00,0.00]  , zDir =[0.00,0.00,1.00]);
    theModel.updateSectionFromSectionCoord( sectionID = S_1.id);
    S_1_SP_1 = theModel.createSecNode( x = 0.00, y = 1.51, z = 30.00, theSect = S_1);
    S_1_SP_2 = theModel.createSecNode( x = 0.00, y = 1.52, z = 13.50, theSect = S_1);
    S_1_SL_1 = theModel.createSecCurve( start = S_1_SP_1, end = S_1_SP_2, theSect = S_1);
    S_1_SP_3 = theModel.createSecNode( x = 0.00, y = 37.51, z = 13.50, theSect = S_1);
    S_1_SL_2 = theModel.createSecCurve( start = S_1_SP_2, end = S_1_SP_3, theSect = S_1);
    S_1_SP_4 = theModel.createSecNode( x = 0.00, y = 40.51, z = 10.50, theSect = S_1);
    S_1_SL_3 = theModel.createSecCurve( start = S_1_SP_3, end = S_1_SP_4, theSect = S_1);
    S_1_SP_5 = theModel.createSecNode( x = 0.00, y = 40.51, z = -12.12, theSect = S_1);
    S_1_SL_4 = theModel.createSecCurve( start = S_1_SP_4, end = S_1_SP_5, theSect = S_1);
    S_1_SP_6 = theModel.createSecNode( x = 0.00, y = 40.51, z = -42.88, theSect = S_1);
    S_1_SL_5 = theModel.createSecCurve( start = S_1_SP_5, end = S_1_SP_6, theSect = S_1);
    S_1_SP_7 = theModel.createSecNode( x = 0.00, y = 40.51, z = -65.50, theSect = S_1);
    S_1_SL_6 = theModel.createSecCurve( start = S_1_SP_6, end = S_1_SP_7, theSect = S_1);
    S_1_SP_8 = theModel.createSecNode( x = 0.00, y = 37.52, z = -68.50, theSect = S_1);
    S_1_SL_7 = theModel.createSecCurve( start = S_1_SP_7, end = S_1_SP_8, theSect = S_1);
    S_1_SP_9 = theModel.createSecNode( x = 0.00, y = 1.51, z = -68.50, theSect = S_1);
    S_1_SL_8 = theModel.createSecCurve( start = S_1_SP_8, end = S_1_SP_9, theSect = S_1);
    S_1_SP_10 = theModel.createSecNode( x = 0.00, y = 1.51, z = -75.00, theSect = S_1);
    S_1_SL_9 = theModel.createSecCurve( start = S_1_SP_9, end = S_1_SP_10, theSect = S_1);
    S_1_SP_11 = theModel.createSecNode( x = 0.00, y = 1.51, z = -8.07, theSect = S_1);
    S_1_SL_10 = theModel.createSecCurve( start = S_1_SP_2, end = S_1_SP_11, theSect = S_1);
    S_1_SP_12 = theModel.createSecNode( x = 0.00, y = 2.71, z = -10.41, theSect = S_1);
    S_1_SL_11 = theModel.createSecCurve( start = S_1_SP_11, end = S_1_SP_12, theSect = S_1);
    S_1_SP_13 = theModel.createSecNode( x = 0.00, y = 7.51, z = -11.54, theSect = S_1);
    S_1_SL_12 = theModel.createSecCurve( start = S_1_SP_12, end = S_1_SP_13, theSect = S_1);
    S_1_SP_14 = theModel.createSecNode( x = 0.00, y = 7.51, z = -43.46, theSect = S_1);
    S_1_SL_13 = theModel.createSecCurve( start = S_1_SP_13, end = S_1_SP_14, theSect = S_1);
    S_1_SP_15 = theModel.createSecNode( x = 0.00, y = 2.71, z = -44.59, theSect = S_1);
    S_1_SL_14 = theModel.createSecCurve( start = S_1_SP_14, end = S_1_SP_15, theSect = S_1);
    S_1_SP_16 = theModel.createSecNode( x = 0.00, y = 1.51, z = -46.93, theSect = S_1);
    S_1_SL_15 = theModel.createSecCurve( start = S_1_SP_15, end = S_1_SP_16, theSect = S_1);
    S_1_SL_16 = theModel.createSecCurve( start = S_1_SP_16, end = S_1_SP_9, theSect = S_1);
    S_1_SL_17 = theModel.createSecCurve( start = S_1_SP_13, end = S_1_SP_5, theSect = S_1);
    S_1_SL_18 = theModel.createSecCurve( start = S_1_SP_14, end = S_1_SP_6, theSect = S_1);
    theModel.drawModel();

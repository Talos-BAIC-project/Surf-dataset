# 
#           DFC Script 
# ============================= 
#   Description: 
#          Date: 2026-07-27 12:23:52
#       Version: Wranger 4.4.34.24527
# 
    G_1 = theModel.createSurfaceGroup(); 

    S_1 = theModel.createSect( sectionName = "S_1");
    theModel.setSecCoordSys( id = S_1.id, orig = [0.00 , 0.00 , 0.00] , xDir = [1.00,0.00,0.00] , yDir =[0.00,1.00,0.00]  , zDir =[0.00,0.00,1.00]);
    theModel.updateSectionFromSectionCoord( sectionID = S_1.id);
    theModel.setSecCoordSys( id = S_1.id, orig = [0.00 , 0.00 , 0.00] , xDir = [0.00,1.00,0.00] , yDir =[-1.00,0.00,0.00]  , zDir =[0.00,0.00,1.00]);
    theModel.updateSectionFromSectionCoord( sectionID = S_1.id);
    S_1_SP_1 = theModel.createSecNode( x = 0.00, y = 781.42, z = 247.10, theSect = S_1);
    S_1_SP_2 = theModel.createSecNode( x = 0.00, y = 785.72, z = 242.80, theSect = S_1);
    S_1_SL_1 = theModel.createSecCurve( start = S_1_SP_1, end = S_1_SP_2, theSect = S_1);
    S_1_SP_3 = theModel.createSecNode( x = 0.00, y = 785.72, z = 152.80, theSect = S_1);
    S_1_SL_2 = theModel.createSecCurve( start = S_1_SP_2, end = S_1_SP_3, theSect = S_1);
    S_1_SP_4 = theModel.createSecNode( x = 0.00, y = 781.41, z = 148.50, theSect = S_1);
    S_1_SL_3 = theModel.createSecCurve( start = S_1_SP_3, end = S_1_SP_4, theSect = S_1);
    S_1_SP_5 = theModel.createSecNode( x = 0.00, y = 761.42, z = 148.50, theSect = S_1);
    S_1_SL_4 = theModel.createSecCurve( start = S_1_SP_4, end = S_1_SP_5, theSect = S_1);
    S_1_SP_6 = theModel.createSecNode( x = 0.00, y = 757.12, z = 152.80, theSect = S_1);
    S_1_SL_5 = theModel.createSecCurve( start = S_1_SP_5, end = S_1_SP_6, theSect = S_1);
    S_1_SP_7 = theModel.createSecNode( x = 0.00, y = 757.12, z = 193.80, theSect = S_1);
    S_1_SL_6 = theModel.createSecCurve( start = S_1_SP_6, end = S_1_SP_7, theSect = S_1);
    S_1_SP_8 = theModel.createSecNode( x = 0.00, y = 761.42, z = 198.10, theSect = S_1);
    S_1_SL_7 = theModel.createSecCurve( start = S_1_SP_7, end = S_1_SP_8, theSect = S_1);
    S_1_SP_9 = theModel.createSecNode( x = 0.00, y = 780.62, z = 198.10, theSect = S_1);
    S_1_SL_8 = theModel.createSecCurve( start = S_1_SP_8, end = S_1_SP_9, theSect = S_1);
    S_1_SP_10 = theModel.createSecNode( x = 0.00, y = 784.32, z = 201.80, theSect = S_1);
    S_1_SL_9 = theModel.createSecCurve( start = S_1_SP_9, end = S_1_SP_10, theSect = S_1);
    S_1_SP_11 = theModel.createSecNode( x = 0.00, y = 784.32, z = 210.80, theSect = S_1);
    S_1_SL_10 = theModel.createSecCurve( start = S_1_SP_10, end = S_1_SP_11, theSect = S_1);
    S_1_SP_12 = theModel.createSecNode( x = 0.00, y = 780.61, z = 214.50, theSect = S_1);
    S_1_SL_11 = theModel.createSecCurve( start = S_1_SP_11, end = S_1_SP_12, theSect = S_1);
    S_1_SP_13 = theModel.createSecNode( x = 0.00, y = 761.41, z = 214.50, theSect = S_1);
    S_1_SL_12 = theModel.createSecCurve( start = S_1_SP_12, end = S_1_SP_13, theSect = S_1);
    S_1_SP_14 = theModel.createSecNode( x = 0.00, y = 757.12, z = 218.80, theSect = S_1);
    S_1_SL_13 = theModel.createSecCurve( start = S_1_SP_13, end = S_1_SP_14, theSect = S_1);
    S_1_SP_15 = theModel.createSecNode( x = 0.00, y = 757.12, z = 242.80, theSect = S_1);
    S_1_SL_14 = theModel.createSecCurve( start = S_1_SP_14, end = S_1_SP_15, theSect = S_1);
    S_1_SP_16 = theModel.createSecNode( x = 0.00, y = 761.41, z = 247.10, theSect = S_1);
    S_1_SL_15 = theModel.createSecCurve( start = S_1_SP_15, end = S_1_SP_16, theSect = S_1);
    S_1_SL_16 = theModel.createSecCurve( start = S_1_SP_16, end = S_1_SP_1, theSect = S_1);
    theModel.drawModel();

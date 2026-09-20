#
#           DFC Script
# =============================
#   Description: Generated from DFCModel
#          Date: 2026-07-29 11:51:14
#       Version: 4.4.34
#
    S_3 = theModel.createSect( sectionName = "S_1");
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 0.00, z = 0.00, theSect = S_3);
    S_3_SP_4 = theModel.createSecNode( x = 0.00, y = 1.00, z = 45.98, theSect = S_3);
    S_3_SP_5 = theModel.createSecNode( x = 0.00, y = 6.04, z = 49.85, theSect = S_3);
    S_3_SP_8 = theModel.createSecNode( x = 0.00, y = 28.17, z = 34.67, theSect = S_3);
    S_3_SP_11 = theModel.createSecNode( x = 0.00, y = 28.58, z = 25.16, theSect = S_3);
    S_3_SP_14 = theModel.createSecNode( x = 0.00, y = 8.95, z = 8.51, theSect = S_3);
    S_3_SP_17 = theModel.createSecNode( x = 0.00, y = 5.00, z = 2.88, theSect = S_3);
    S_3_SP_20 = theModel.createSecNode( x = 0.00, y = 5.00, z = -2.88, theSect = S_3);
    S_3_SP_23 = theModel.createSecNode( x = 0.00, y = 8.95, z = -8.51, theSect = S_3);
    S_3_SP_26 = theModel.createSecNode( x = 0.00, y = 28.58, z = -25.16, theSect = S_3);
    S_3_SP_29 = theModel.createSecNode( x = 0.00, y = 28.17, z = -34.67, theSect = S_3);
    S_3_SP_32 = theModel.createSecNode( x = 0.00, y = 6.04, z = -49.85, theSect = S_3);
    S_3_SP_35 = theModel.createSecNode( x = 0.00, y = 1.00, z = -45.98, theSect = S_3);
    S_3_SL_1 = theModel.createSecCurve( start = S_3_SP_4, end = S_3_SP_5, theSect = S_3);
    S_3_SL_2 = theModel.createSecCurve( start = S_3_SP_5, end = S_3_SP_8, theSect = S_3);
    S_3_SL_3 = theModel.createSecCurve( start = S_3_SP_8, end = S_3_SP_11, theSect = S_3);
    S_3_SL_4 = theModel.createSecCurve( start = S_3_SP_11, end = S_3_SP_14, theSect = S_3);
    S_3_SL_5 = theModel.createSecCurve( start = S_3_SP_14, end = S_3_SP_17, theSect = S_3);
    S_3_SL_6 = theModel.createSecCurve( start = S_3_SP_17, end = S_3_SP_20, theSect = S_3);
    S_3_SL_7 = theModel.createSecCurve( start = S_3_SP_20, end = S_3_SP_23, theSect = S_3);
    S_3_SL_8 = theModel.createSecCurve( start = S_3_SP_23, end = S_3_SP_26, theSect = S_3);
    S_3_SL_9 = theModel.createSecCurve( start = S_3_SP_26, end = S_3_SP_29, theSect = S_3);
    S_3_SL_10 = theModel.createSecCurve( start = S_3_SP_29, end = S_3_SP_32, theSect = S_3);
    S_3_SL_11 = theModel.createSecCurve( start = S_3_SP_32, end = S_3_SP_35, theSect = S_3);
    S_3_SL_12 = theModel.createSecCurve( start = S_3_SP_35, end = S_3_SP_4, theSect = S_3);
    theModel.drawModel();

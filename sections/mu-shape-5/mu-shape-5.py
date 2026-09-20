#
#           DFC Script
# =============================
#   Description: Generated from DFCModel
#          Date: 2026-07-29 09:40:34
#       Version: 4.4.34
#
    S_3 = theModel.createSect( sectionName = "S_1");
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 0.00, z = 0.00, theSect = S_3);
    S_3_SP_4 = theModel.createSecNode( x = -752.09, y = 0.00, z = 280.30, theSect = S_3);
    S_3_SP_5 = theModel.createSecNode( x = -752.09, y = 0.00, z = 268.80, theSect = S_3);
    S_3_SP_8 = theModel.createSecNode( x = -752.09, y = 0.00, z = 220.05, theSect = S_3);
    S_3_SP_11 = theModel.createSecNode( x = -752.09, y = 0.00, z = 170.55, theSect = S_3);
    S_3_SP_14 = theModel.createSecNode( x = -752.09, y = 0.00, z = 125.05, theSect = S_3);
    S_3_SP_17 = theModel.createSecNode( x = -748.85, y = 0.00, z = 121.80, theSect = S_3);
    S_3_SP_20 = theModel.createSecNode( x = -711.84, y = 0.00, z = 121.80, theSect = S_3);
    S_3_SP_23 = theModel.createSecNode( x = -708.59, y = 0.00, z = 125.05, theSect = S_3);
    S_3_SP_26 = theModel.createSecNode( x = -708.59, y = 0.00, z = 170.55, theSect = S_3);
    S_3_SP_29 = theModel.createSecNode( x = -708.59, y = 0.00, z = 220.05, theSect = S_3);
    S_3_SP_32 = theModel.createSecNode( x = -708.59, y = 0.00, z = 265.55, theSect = S_3);
    S_3_SP_35 = theModel.createSecNode( x = -711.84, y = 0.00, z = 268.80, theSect = S_3);
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
    S_3_SL_12 = theModel.createSecCurve( start = S_3_SP_35, end = S_3_SP_5, theSect = S_3);
    S_3_SL_13 = theModel.createSecCurve( start = S_3_SP_8, end = S_3_SP_29, theSect = S_3);
    S_3_SL_14 = theModel.createSecCurve( start = S_3_SP_26, end = S_3_SP_11, theSect = S_3);
    theModel.drawModel();

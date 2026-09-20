#
#           DFC Script
# =============================
#   Description: Generated from DFCModel
#          Date: 2026-07-29
#       Version: 4.4.34
#
    S_3 = theModel.createSect( sectionName = "S_1");
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 0.00, z = 0.00, theSect = S_3);
    S_3_SP_1 = theModel.createSecNode( x = 0.00, y = 1.25, z = 51.60, theSect = S_3);
    S_3_SP_2 = theModel.createSecNode( x = 0.00, y = 1.25, z = 41.25, theSect = S_3);
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 6.25, z = 36.25, theSect = S_3);
    S_3_SP_4 = theModel.createSecNode( x = 0.00, y = 31.25, z = 36.25, theSect = S_3);
    S_3_SP_5 = theModel.createSecNode( x = 0.00, y = 36.25, z = 31.25, theSect = S_3);
    S_3_SP_6 = theModel.createSecNode( x = 0.00, y = 36.25, z = 18.02, theSect = S_3);
    S_3_SP_7 = theModel.createSecNode( x = 0.00, y = 34.79, z = 14.48, theSect = S_3);
    S_3_SP_8 = theModel.createSecNode( x = 0.00, y = 26.25, z = 2.63, theSect = S_3);
    S_3_SP_9 = theModel.createSecNode( x = 0.00, y = 26.25, z = -21.17, theSect = S_3);
    S_3_SP_10 = theModel.createSecNode( x = 0.00, y = 28.59, z = -26.82, theSect = S_3);
    S_3_SP_11 = theModel.createSecNode( x = 0.00, y = 34.79, z = -33.02, theSect = S_3);
    S_3_SP_12 = theModel.createSecNode( x = 0.00, y = 36.25, z = -36.55, theSect = S_3);
    S_3_SP_13 = theModel.createSecNode( x = 0.00, y = 36.25, z = -56.25, theSect = S_3);
    S_3_SP_14 = theModel.createSecNode( x = 0.00, y = 31.25, z = -61.25, theSect = S_3);
    S_3_SP_15 = theModel.createSecNode( x = 0.00, y = 6.25, z = -61.25, theSect = S_3);
    S_3_SP_16 = theModel.createSecNode( x = 0.00, y = 1.25, z = -66.25, theSect = S_3);
    S_3_SP_17 = theModel.createSecNode( x = 0.00, y = 1.25, z = -77.40, theSect = S_3);
    S_3_SL_1 = theModel.createSecCurve( start = S_3_SP_1, end = S_3_SP_2, theSect = S_3);
    S_3_SL_2 = theModel.createSecCurve( start = S_3_SP_2, end = S_3_SP_3, theSect = S_3);
    S_3_SL_3 = theModel.createSecCurve( start = S_3_SP_3, end = S_3_SP_4, theSect = S_3);
    S_3_SL_4 = theModel.createSecCurve( start = S_3_SP_4, end = S_3_SP_5, theSect = S_3);
    S_3_SL_5 = theModel.createSecCurve( start = S_3_SP_5, end = S_3_SP_6, theSect = S_3);
    S_3_SL_6 = theModel.createSecCurve( start = S_3_SP_6, end = S_3_SP_7, theSect = S_3);
    S_3_SL_7 = theModel.createSecCurve( start = S_3_SP_7, end = S_3_SP_8, theSect = S_3);
    S_3_SL_8 = theModel.createSecCurve( start = S_3_SP_8, end = S_3_SP_9, theSect = S_3);
    S_3_SL_9 = theModel.createSecCurve( start = S_3_SP_9, end = S_3_SP_10, theSect = S_3);
    S_3_SL_10 = theModel.createSecCurve( start = S_3_SP_10, end = S_3_SP_11, theSect = S_3);
    S_3_SL_11 = theModel.createSecCurve( start = S_3_SP_11, end = S_3_SP_12, theSect = S_3);
    S_3_SL_12 = theModel.createSecCurve( start = S_3_SP_12, end = S_3_SP_13, theSect = S_3);
    S_3_SL_13 = theModel.createSecCurve( start = S_3_SP_13, end = S_3_SP_14, theSect = S_3);
    S_3_SL_14 = theModel.createSecCurve( start = S_3_SP_14, end = S_3_SP_15, theSect = S_3);
    S_3_SL_15 = theModel.createSecCurve( start = S_3_SP_15, end = S_3_SP_16, theSect = S_3);
    S_3_SL_16 = theModel.createSecCurve( start = S_3_SP_16, end = S_3_SP_17, theSect = S_3);
    theModel.drawModel();

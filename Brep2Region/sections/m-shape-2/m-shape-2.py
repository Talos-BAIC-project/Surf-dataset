#
#           DFC Script
# =============================
#   Description: Generated from DFCModel
#          Date: 2026-07-29 11:51:14
#       Version: 4.4.34
#
    S_3 = theModel.createSect( sectionName = "S_1");
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 0.00, z = 0.00, theSect = S_3);
    S_3_SP_4 = theModel.createSecNode( x = 0.00, y = 15.00, z = 44.25, theSect = S_3);
    S_3_SP_5 = theModel.createSecNode( x = 0.00, y = 3.75, z = 44.25, theSect = S_3);
    S_3_SP_8 = theModel.createSecNode( x = 0.00, y = 0.75, z = 41.25, theSect = S_3);
    S_3_SP_11 = theModel.createSecNode( x = 0.00, y = 0.75, z = 23.75, theSect = S_3);
    S_3_SP_14 = theModel.createSecNode( x = 0.00, y = 3.75, z = 20.75, theSect = S_3);
    S_3_SP_17 = theModel.createSecNode( x = 0.00, y = 5.98, z = 20.75, theSect = S_3);
    S_3_SP_20 = theModel.createSecNode( x = 0.00, y = 8.75, z = 17.75, theSect = S_3);
    S_3_SP_23 = theModel.createSecNode( x = 0.00, y = 8.75, z = -17.75, theSect = S_3);
    S_3_SP_26 = theModel.createSecNode( x = 0.00, y = 5.93, z = -20.75, theSect = S_3);
    S_3_SP_29 = theModel.createSecNode( x = 0.00, y = 3.73, z = -20.75, theSect = S_3);
    S_3_SP_32 = theModel.createSecNode( x = 0.00, y = 0.75, z = -23.75, theSect = S_3);
    S_3_SP_35 = theModel.createSecNode( x = 0.00, y = 0.75, z = -41.25, theSect = S_3);
    S_3_SP_38 = theModel.createSecNode( x = 0.00, y = 3.75, z = -44.25, theSect = S_3);
    S_3_SP_41 = theModel.createSecNode( x = 0.00, y = 15.00, z = -44.25, theSect = S_3);
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
    S_3_SL_12 = theModel.createSecCurve( start = S_3_SP_35, end = S_3_SP_38, theSect = S_3);
    S_3_SL_13 = theModel.createSecCurve( start = S_3_SP_38, end = S_3_SP_41, theSect = S_3);
    theModel.drawModel();

#
#           DFC Script
# =============================
#   Description: Generated from DFCModel
#          Date: 2026-07-29
#       Version: 4.4.34
#
    S_3 = theModel.createSect( sectionName = "S_1");
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 0.00, z = 0.00, theSect = S_3);
    S_3_SP_1 = theModel.createSecNode( x = -1111.00, y = 0.00, z = 145.78, theSect = S_3);
    S_3_SP_2 = theModel.createSecNode( x = -1114.34, y = 0.00, z = 142.53, theSect = S_3);
    S_3_SP_3 = theModel.createSecNode( x = -1114.34, y = 0.00, z = 91.93, theSect = S_3);
    S_3_SP_4 = theModel.createSecNode( x = -1114.34, y = 0.00, z = 41.32, theSect = S_3);
    S_3_SP_5 = theModel.createSecNode( x = -1111.02, y = 0.00, z = 38.09, theSect = S_3);
    S_3_SP_6 = theModel.createSecNode( x = -1075.95, y = 0.00, z = 38.09, theSect = S_3);
    S_3_SP_7 = theModel.createSecNode( x = -1072.64, y = 0.00, z = 41.31, theSect = S_3);
    S_3_SP_8 = theModel.createSecNode( x = -1072.64, y = 0.00, z = 91.93, theSect = S_3);
    S_3_SP_9 = theModel.createSecNode( x = -1072.64, y = 0.00, z = 142.55, theSect = S_3);
    S_3_SP_10 = theModel.createSecNode( x = -1075.95, y = 0.00, z = 145.78, theSect = S_3);
    S_3_SL_1 = theModel.createSecCurve( start = S_3_SP_1, end = S_3_SP_2, theSect = S_3);
    S_3_SL_2 = theModel.createSecCurve( start = S_3_SP_2, end = S_3_SP_3, theSect = S_3);
    S_3_SL_3 = theModel.createSecCurve( start = S_3_SP_3, end = S_3_SP_4, theSect = S_3);
    S_3_SL_4 = theModel.createSecCurve( start = S_3_SP_4, end = S_3_SP_5, theSect = S_3);
    S_3_SL_5 = theModel.createSecCurve( start = S_3_SP_5, end = S_3_SP_6, theSect = S_3);
    S_3_SL_6 = theModel.createSecCurve( start = S_3_SP_6, end = S_3_SP_7, theSect = S_3);
    S_3_SL_7 = theModel.createSecCurve( start = S_3_SP_7, end = S_3_SP_8, theSect = S_3);
    S_3_SL_8 = theModel.createSecCurve( start = S_3_SP_8, end = S_3_SP_9, theSect = S_3);
    S_3_SL_9 = theModel.createSecCurve( start = S_3_SP_9, end = S_3_SP_10, theSect = S_3);
    S_3_SL_10 = theModel.createSecCurve( start = S_3_SP_10, end = S_3_SP_1, theSect = S_3);
    S_3_SL_11 = theModel.createSecCurve( start = S_3_SP_3, end = S_3_SP_8, theSect = S_3);
    theModel.drawModel();

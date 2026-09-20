#
#           DFC Script
# =============================
#   Description: Generated from DFCModel
#          Date: 2026-07-29
#       Version: 4.4.34
#
    S_3 = theModel.createSect( sectionName = "S_1");
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 0.00, z = 0.00, theSect = S_3);
    S_3_SP_1 = theModel.createSecNode( x = 0.00, y = 1.51, z = 70.00, theSect = S_3);
    S_3_SP_2 = theModel.createSecNode( x = 0.00, y = 1.52, z = 27.44, theSect = S_3);
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 40.01, z = 27.50, theSect = S_3);
    S_3_SP_4 = theModel.createSecNode( x = 0.00, y = 43.51, z = 24.00, theSect = S_3);
    S_3_SP_5 = theModel.createSecNode( x = 0.00, y = 43.51, z = -24.00, theSect = S_3);
    S_3_SP_6 = theModel.createSecNode( x = 0.00, y = 40.01, z = -27.50, theSect = S_3);
    S_3_SP_7 = theModel.createSecNode( x = 0.00, y = 1.52, z = -27.44, theSect = S_3);
    S_3_SP_8 = theModel.createSecNode( x = 0.00, y = 1.51, z = -70.00, theSect = S_3);
    S_3_SL_1 = theModel.createSecCurve( start = S_3_SP_1, end = S_3_SP_2, theSect = S_3);
    S_3_SL_2 = theModel.createSecCurve( start = S_3_SP_2, end = S_3_SP_3, theSect = S_3);
    S_3_SL_3 = theModel.createSecCurve( start = S_3_SP_3, end = S_3_SP_4, theSect = S_3);
    S_3_SL_4 = theModel.createSecCurve( start = S_3_SP_4, end = S_3_SP_5, theSect = S_3);
    S_3_SL_5 = theModel.createSecCurve( start = S_3_SP_5, end = S_3_SP_6, theSect = S_3);
    S_3_SL_6 = theModel.createSecCurve( start = S_3_SP_6, end = S_3_SP_7, theSect = S_3);
    S_3_SL_7 = theModel.createSecCurve( start = S_3_SP_7, end = S_3_SP_8, theSect = S_3);
    S_3_SL_8 = theModel.createSecCurve( start = S_3_SP_2, end = S_3_SP_7, theSect = S_3);
    theModel.drawModel();

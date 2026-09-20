#
#           DFC Script
# =============================
#   Description: Generated from DFCModel
#          Date: 2026-07-28 18:48:14
#       Version: 4.4.34
#
    S_3 = theModel.createSect( sectionName = "S_1");
    S_3_SP_3 = theModel.createSecNode( x = 2938.87, y = -773.20, z = 695.74, theSect = S_3);
    S_3_SP_4 = theModel.createSecNode( x = 2938.87, y = -773.20, z = 695.74, theSect = S_3);
    S_3_SP_5 = theModel.createSecNode( x = 2998.60, y = -773.20, z = 695.74, theSect = S_3);
    S_3_SP_6 = theModel.createSecNode( x = 3005.50, y = -856.21, z = 695.74, theSect = S_3);
    S_3_SP_7 = theModel.createSecNode( x = 3197.06, y = -769.90, z = 695.74, theSect = S_3);
    S_3_SP_8 = theModel.createSecNode( x = 3167.57, y = -769.90, z = 695.74, theSect = S_3);
    S_3_SP_9 = theModel.createSecNode( x = 3156.29, y = -845.35, z = 695.74, theSect = S_3);
    S_3_SL_1 = theModel.createSecCurve( start = S_3_SP_4, end = S_3_SP_5, theSect = S_3);
    S_3_SL_2 = theModel.createSecCurve( start = S_3_SP_5, end = S_3_SP_6, theSect = S_3);
    S_3_SL_3 = theModel.createSecCurve( start = S_3_SP_7, end = S_3_SP_8, theSect = S_3);
    S_3_SL_4 = theModel.createSecCurve( start = S_3_SP_8, end = S_3_SP_9, theSect = S_3);
    S_3_SL_5 = theModel.createSecCurve( start = S_3_SP_6, end = S_3_SP_9, theSect = S_3);
    theModel.drawModel();
